"""客户预约创建与幂等处理。"""

from __future__ import annotations

from datetime import timedelta

from catalog.models import Service
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone
from tenants.models import Tenant, TenantCustomer

from scheduling.constants import BookingConfirmationMode
from scheduling.models import (
    Booking,
    BookingStatus,
    TimeSlot,
    TimeSlotStatus,
)
from scheduling.services.booking import ACTIVE_BOOKING_STATUSES
from scheduling.services.booking_settings import scheduling_booking_settings_get_for_tenant


def scheduling_booking_create(
    *,
    tenant: Tenant,
    customer: TenantCustomer,
    idempotency_key: str,
    service_id: int,
    party_size: int,
    time_slot_id: int | None = None,
    location_id: int | None = None,
    start=None,
    end=None,
    resource_id: int | None = None,
    contact_name: str = "",
    contact_phone: str = "",
) -> Booking:
    """创建客户预约，按租户确认模式设为 CONFIRMED 或 PENDING。

    在 MySQL 事务内锁定时段并校验容量与业务规则；同一客户、同一时段不可重复有效预约；
    相同幂等键重试返回首次创建结果。人工确认模式下 PENDING 预约预占容量并记录过期时间。

    Args:
        tenant (Tenant): 目标租户。
        customer (TenantCustomer): 下单客户档案。
        idempotency_key (str): 请求幂等键。
        service_id (int): 服务项目 ID。
        party_size (int): 预约人数。
        time_slot_id (int | None): 指定固定时段 ID。
        location_id (int | None): 未指定时段时用于匹配地点。
        start: 未指定时段时的开始时间（UTC）。
        end: 未指定时段时的结束时间（UTC）。
        resource_id (int | None): 可选指定资源；省略时自动分配。
        contact_name (str): 代他人预约时的联系人姓名。
        contact_phone (str): 代他人预约时的联系人手机号。

    Returns:
        Booking: 新建或幂等重放的预约。

    Raises:
        ValidationError: 参数无效、容量不足或重复预约。
    """
    existing = (
        Booking.objects.filter(
            tenant=tenant,
            customer=customer,
            idempotency_key=idempotency_key,
        )
        .select_related("time_slot", "service")
        .first()
    )
    if existing is not None:
        return existing

    try:
        service = Service.objects.prefetch_related("resources").get(
            tenant=tenant,
            id=service_id,
            is_active=True,
        )
    except Service.DoesNotExist as exc:
        raise ValidationError("服务项目不存在或未启用。") from exc

    with transaction.atomic():
        if time_slot_id is not None:
            time_slot = (
                TimeSlot.objects.select_for_update()
                .select_related("resource", "location")
                .get(tenant=tenant, id=time_slot_id)
            )
        else:
            time_slot = _scheduling_booking_resolve_time_slot(
                tenant=tenant,
                service=service,
                location_id=location_id,
                start=start,
                end=end,
                resource_id=resource_id,
            )

        _scheduling_booking_validate_time_slot(
            time_slot=time_slot,
            service=service,
            resource_id=resource_id,
        )
        _scheduling_booking_validate_customer_slot(
            customer=customer,
            time_slot=time_slot,
        )
        _scheduling_booking_validate_capacity(
            time_slot=time_slot,
            party_size=party_size,
        )

        settings = scheduling_booking_settings_get_for_tenant(tenant=tenant)
        _scheduling_booking_validate_booking_rules(
            customer=customer,
            time_slot=time_slot,
            settings=settings,
        )

        status = BookingStatus.CONFIRMED
        pending_expires_at = None
        if settings.confirmation_mode == BookingConfirmationMode.MANUAL:
            status = BookingStatus.PENDING
            pending_expires_at = timezone.now() + timedelta(
                minutes=settings.pending_retention_minutes
            )

        booking = Booking.objects.create(
            tenant=tenant,
            customer=customer,
            time_slot=time_slot,
            service=service,
            status=status,
            party_size=party_size,
            contact_name=contact_name.strip(),
            contact_phone=contact_phone.strip(),
            idempotency_key=idempotency_key,
            pending_expires_at=pending_expires_at,
        )
        from notifications.services.booking_hooks import (
            notifications_booking_outbox_write_for_create,
        )

        notifications_booking_outbox_write_for_create(booking=booking)
        return booking


def _scheduling_booking_resolve_time_slot(
    *,
    tenant: Tenant,
    service: Service,
    location_id: int | None,
    start,
    end,
    resource_id: int | None,
) -> TimeSlot:
    """按服务与时间解析或自动分配固定时段。

    Args:
        tenant (Tenant): 目标租户。
        service (Service): 服务项目。
        location_id (int | None): 地点 ID。
        start: 时段开始（UTC）。
        end: 时段结束（UTC）。
        resource_id (int | None): 可选资源 ID。

    Returns:
        TimeSlot: 已锁定的固定时段。

    Raises:
        ValidationError: 无法匹配可用时段。
    """
    if location_id is None or start is None or end is None:
        raise ValidationError("未指定时段时必须提供 location_id、start 与 end。")

    service_resource_ids = {resource.id for resource in service.resources.all()}
    candidate_slots = list(
        TimeSlot.objects.select_for_update()
        .filter(
            tenant=tenant,
            location_id=location_id,
            status=TimeSlotStatus.OPEN,
            start=start,
            end=end,
            resource_id__in=service_resource_ids,
        )
        .select_related("resource", "location")
        .order_by("resource_id")
    )
    if resource_id is not None:
        candidate_slots = [slot for slot in candidate_slots if slot.resource_id == resource_id]

    available_slots = [
        slot
        for slot in candidate_slots
        if _scheduling_booking_remaining_capacity(time_slot=slot) > 0
    ]
    if not available_slots:
        raise ValidationError("该时段容量不足或不可用。")

    if resource_id is not None:
        return available_slots[0]

    return _scheduling_booking_pick_lowest_load_slot(slots=available_slots)


def _scheduling_booking_pick_lowest_load_slot(*, slots: list[TimeSlot]) -> TimeSlot:
    """在候选时段中选择负载最低的资源对应时段。

    负载相同时按资源 ID 稳定排序。

    Args:
        slots (list[TimeSlot]): 可用固定时段列表。

    Returns:
        TimeSlot: 选中的固定时段。
    """
    load_by_resource: dict[int, int] = {}
    for slot in slots:
        load = _scheduling_booking_resource_active_load(resource_id=slot.resource_id)
        load_by_resource[slot.resource_id] = load

    return min(
        slots,
        key=lambda slot: (load_by_resource[slot.resource_id], slot.resource_id),
    )


def _scheduling_booking_resource_active_load(*, resource_id: int) -> int:
    """统计资源当前有效预约总数（按 party_size 计）。

    Args:
        resource_id (int): 资源 ID。

    Returns:
        int: 有效预约人数合计。
    """
    total = (
        Booking.objects.filter(
            time_slot__resource_id=resource_id,
            status__in=ACTIVE_BOOKING_STATUSES,
        ).aggregate(total=Sum("party_size"))["total"]
        or 0
    )
    return total


def _scheduling_booking_remaining_capacity(*, time_slot: TimeSlot) -> int:
    """计算时段剩余容量。

    Args:
        time_slot (TimeSlot): 固定时段。

    Returns:
        int: 剩余可预约人数。
    """
    used = (
        Booking.objects.filter(
            time_slot=time_slot,
            status__in=ACTIVE_BOOKING_STATUSES,
        ).aggregate(total=Sum("party_size"))["total"]
        or 0
    )
    return max(0, time_slot.capacity - used)


def _scheduling_booking_validate_time_slot(
    *,
    time_slot: TimeSlot,
    service: Service,
    resource_id: int | None,
) -> None:
    """校验时段开放且服务、资源可预约。

    Args:
        time_slot (TimeSlot): 固定时段。
        service (Service): 服务项目。
        resource_id (int | None): 请求指定的资源 ID。

    Raises:
        ValidationError: 时段不可用或服务/资源不匹配。
    """
    if time_slot.status != TimeSlotStatus.OPEN:
        raise ValidationError("固定时段已关闭，无法预约。")

    service_resource_ids = {resource.id for resource in service.resources.all()}
    if time_slot.resource_id not in service_resource_ids:
        raise ValidationError("该服务不可在此资源上预约。")

    if resource_id is not None and time_slot.resource_id != resource_id:
        raise ValidationError("指定资源与时段不匹配。")


def _scheduling_booking_validate_customer_slot(
    *,
    customer: TenantCustomer,
    time_slot: TimeSlot,
) -> None:
    """校验客户在同一时段没有其它有效预约。

    Args:
        customer (TenantCustomer): 客户档案。
        time_slot (TimeSlot): 固定时段。

    Raises:
        ValidationError: 已存在有效预约。
    """
    if Booking.objects.filter(
        customer=customer,
        time_slot=time_slot,
        status__in=ACTIVE_BOOKING_STATUSES,
    ).exists():
        raise ValidationError("您在该时段已有有效预约。")


def _scheduling_booking_validate_capacity(
    *,
    time_slot: TimeSlot,
    party_size: int,
) -> None:
    """校验时段剩余容量是否足够。

    Args:
        time_slot (TimeSlot): 固定时段。
        party_size (int): 预约人数。

    Raises:
        ValidationError: 容量不足。
    """
    if _scheduling_booking_remaining_capacity(time_slot=time_slot) < party_size:
        raise ValidationError("该时段容量不足。")


def _scheduling_booking_validate_booking_rules(
    *,
    customer: TenantCustomer,
    time_slot: TimeSlot,
    settings,
) -> None:
    """校验租户预约业务规则（窗口、未来预约上限）。

    Args:
        customer (TenantCustomer): 客户档案。
        time_slot (TimeSlot): 固定时段。
        settings: ``TenantBookingSettings`` 实例。

    Raises:
        ValidationError: 违反业务规则。
    """
    now = timezone.now()
    slot_start = time_slot.start
    if slot_start < now + timedelta(minutes=settings.min_advance_minutes):
        raise ValidationError("预约时间早于允许的最短提前预约时间。")
    if slot_start > now + timedelta(days=settings.max_booking_window_days):
        raise ValidationError("预约时间超出允许的最远可预约范围。")

    future_active_count = Booking.objects.filter(
        customer=customer,
        status__in=ACTIVE_BOOKING_STATUSES,
        time_slot__start__gt=now,
    ).count()
    if future_active_count >= settings.future_booking_limit:
        raise ValidationError("您已达到未来有效预约数量上限。")
