"""预约状态机：确认、拒绝、过期等状态变更。"""

from __future__ import annotations

from datetime import timedelta

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from tenants.models import Tenant

from scheduling.models import Booking, BookingCancelActor, BookingStatus
from scheduling.services.booking import CUSTOMER_MODIFIABLE_BOOKING_STATUSES
from scheduling.services.booking_settings import scheduling_booking_settings_get_for_tenant


def scheduling_booking_get_for_tenant(*, tenant: Tenant, booking_id: int) -> Booking:
    """按 ID 获取租户下的预约。

    Args:
        tenant (Tenant): 目标租户。
        booking_id (int): 预约 ID。

    Returns:
        Booking: 匹配的预约实例。

    Raises:
        Booking.DoesNotExist: 预约不存在。
    """
    return Booking.objects.select_related("time_slot", "service", "customer").get(
        tenant=tenant,
        id=booking_id,
    )


def scheduling_booking_confirm(*, booking: Booking) -> Booking:
    """管理员确认待处理预约。

    Args:
        booking (Booking): 待确认预约。

    Returns:
        Booking: 更新后的预约。

    Raises:
        ValidationError: 当前状态不允许确认。
    """
    if booking.status != BookingStatus.PENDING:
        raise ValidationError("仅待确认预约可被确认。")

    with transaction.atomic():
        booking.status = BookingStatus.CONFIRMED
        booking.pending_expires_at = None
        booking.save(update_fields=["status", "pending_expires_at", "updated_at"])
        from notifications.services.booking_hooks import notifications_booking_outbox_write

        notifications_booking_outbox_write(booking=booking, event_type="booking.confirmed")
    return booking


def scheduling_booking_reject(*, booking: Booking) -> Booking:
    """管理员拒绝待处理预约并释放容量。

    Args:
        booking (Booking): 待确认预约。

    Returns:
        Booking: 更新后的预约。

    Raises:
        ValidationError: 当前状态不允许拒绝。
    """
    if booking.status != BookingStatus.PENDING:
        raise ValidationError("仅待确认预约可被拒绝。")

    booking.status = BookingStatus.REJECTED
    booking.pending_expires_at = None
    booking.save(update_fields=["status", "pending_expires_at", "updated_at"])
    return booking


def scheduling_booking_expire(*, booking: Booking) -> Booking:
    """将超时待确认预约标记为已过期并释放容量。

    Args:
        booking (Booking): 待确认预约。

    Returns:
        Booking: 更新后的预约。

    Raises:
        ValidationError: 当前状态不允许过期或尚未到过期时间。
    """
    if booking.status != BookingStatus.PENDING:
        raise ValidationError("仅待确认预约可被过期。")

    if booking.pending_expires_at is not None and booking.pending_expires_at > timezone.now():
        raise ValidationError("预约尚未到过期时间。")

    booking.status = BookingStatus.EXPIRED
    booking.pending_expires_at = None
    booking.save(update_fields=["status", "pending_expires_at", "updated_at"])
    return booking


def scheduling_booking_expire_overdue_pending(*, tenant: Tenant | None = None) -> int:
    """批量过期已到期的待确认预约。

    Args:
        tenant (Tenant | None): 可选租户过滤；省略时处理全部租户。

    Returns:
        int: 成功过期的预约数量。
    """
    now = timezone.now()
    queryset = Booking.objects.filter(
        status=BookingStatus.PENDING,
        pending_expires_at__lte=now,
    )
    if tenant is not None:
        queryset = queryset.filter(tenant=tenant)

    expired_count = 0
    for booking in queryset.select_for_update().iterator():
        with transaction.atomic():
            locked = Booking.objects.select_for_update().get(pk=booking.pk)
            if locked.status != BookingStatus.PENDING:
                continue
            if locked.pending_expires_at is None or locked.pending_expires_at > now:
                continue
            scheduling_booking_expire(booking=locked)
            expired_count += 1
    return expired_count


def _scheduling_booking_ensure_customer_modifiable(*, booking: Booking) -> None:
    """校验预约可由客户修改（未开始、非终态、未归档）。

    Args:
        booking (Booking): 目标预约。

    Raises:
        ValidationError: 当前状态不允许客户修改。
    """
    if booking.archived_at is not None:
        raise ValidationError("已归档预约不可修改。")
    if booking.status not in CUSTOMER_MODIFIABLE_BOOKING_STATUSES:
        raise ValidationError("当前预约状态不可修改。")


def _scheduling_booking_ensure_before_cancel_deadline(*, booking: Booking) -> None:
    """校验尚未超过租户配置的最晚取消时间。

    Args:
        booking (Booking): 目标预约。

    Raises:
        ValidationError: 已超过最晚取消时间。
    """
    settings = scheduling_booking_settings_get_for_tenant(tenant=booking.tenant)
    deadline = booking.time_slot.start - timedelta(minutes=settings.cancel_deadline_minutes)
    if timezone.now() > deadline:
        raise ValidationError("已超过最晚取消时间，无法自行取消或改期。")


def scheduling_booking_cancel(
    *,
    booking: Booking,
    actor: str,
    reason: str = "",
    operator: User | None = None,
) -> Booking:
    """取消预约并释放容量。

    Args:
        booking (Booking): 待取消预约。
        actor (str): 取消方（``BookingCancelActor`` 值）。
        reason (str): 取消原因。
        operator (User | None): 操作人；客户自助取消时为客户对应用户。

    Returns:
        Booking: 更新后的预约。

    Raises:
        ValidationError: 状态不允许取消或已超过取消截止。
    """
    if actor == BookingCancelActor.CUSTOMER:
        _scheduling_booking_ensure_customer_modifiable(booking=booking)
        _scheduling_booking_ensure_before_cancel_deadline(booking=booking)
    elif booking.status not in CUSTOMER_MODIFIABLE_BOOKING_STATUSES:
        raise ValidationError("当前预约状态不可取消。")

    with transaction.atomic():
        booking.status = BookingStatus.CANCELLED
        booking.cancel_actor = actor
        booking.cancel_reason = reason
        booking.cancel_operator = operator
        booking.pending_expires_at = None
        booking.save(
            update_fields=[
                "status",
                "cancel_actor",
                "cancel_reason",
                "cancel_operator",
                "pending_expires_at",
                "updated_at",
            ]
        )
        from notifications.services.booking_hooks import notifications_booking_outbox_write

        notifications_booking_outbox_write(booking=booking, event_type="booking.cancelled")
    return booking


def scheduling_booking_reschedule(
    *,
    booking: Booking,
    new_time_slot_id: int,
    idempotency_key: str,
) -> Booking:
    """客户改期：先占新时段，再将旧预约标记为 RESCHEDULED。

    新时段占用失败时旧预约保持不变（事务回滚）。

    Args:
        booking (Booking): 待改期预约。
        new_time_slot_id (int): 新固定时段 ID。
        idempotency_key (str): 新预约幂等键。

    Returns:
        Booking: 新创建的预约。

    Raises:
        ValidationError: 不可改期或新时段不可用。
    """
    from scheduling.constants import BookingConfirmationMode
    from scheduling.models import TimeSlot
    from scheduling.services.booking_create import (
        _scheduling_booking_validate_capacity,
        _scheduling_booking_validate_customer_slot,
        _scheduling_booking_validate_time_slot,
    )

    _scheduling_booking_ensure_customer_modifiable(booking=booking)
    _scheduling_booking_ensure_before_cancel_deadline(booking=booking)

    existing = Booking.objects.filter(
        tenant=booking.tenant,
        customer=booking.customer,
        idempotency_key=idempotency_key,
    ).first()
    if existing is not None:
        return existing

    with transaction.atomic():
        locked_booking = (
            Booking.objects.select_for_update()
            .select_related("time_slot", "service", "customer", "tenant")
            .get(pk=booking.pk)
        )
        _scheduling_booking_ensure_customer_modifiable(booking=locked_booking)
        _scheduling_booking_ensure_before_cancel_deadline(booking=locked_booking)

        time_slot = (
            TimeSlot.objects.select_for_update()
            .select_related("resource", "location")
            .get(tenant=locked_booking.tenant, id=new_time_slot_id)
        )
        service = locked_booking.service
        _scheduling_booking_validate_time_slot(
            time_slot=time_slot,
            service=service,
            resource_id=None,
        )
        _scheduling_booking_validate_customer_slot(
            customer=locked_booking.customer,
            time_slot=time_slot,
        )
        _scheduling_booking_validate_capacity(
            time_slot=time_slot,
            party_size=locked_booking.party_size,
        )

        settings = scheduling_booking_settings_get_for_tenant(tenant=locked_booking.tenant)
        _scheduling_booking_validate_booking_rules_for_reschedule(
            booking=locked_booking,
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

        new_booking = Booking.objects.create(
            tenant=locked_booking.tenant,
            customer=locked_booking.customer,
            time_slot=time_slot,
            service=service,
            status=status,
            party_size=locked_booking.party_size,
            contact_name=locked_booking.contact_name,
            contact_phone=locked_booking.contact_phone,
            idempotency_key=idempotency_key,
            pending_expires_at=pending_expires_at,
            rescheduled_from=locked_booking,
        )

        locked_booking.status = BookingStatus.RESCHEDULED
        locked_booking.rescheduled_to = new_booking
        locked_booking.pending_expires_at = None
        locked_booking.save(
            update_fields=[
                "status",
                "rescheduled_to",
                "pending_expires_at",
                "updated_at",
            ]
        )
        from notifications.services.booking_hooks import notifications_booking_outbox_write

        notifications_booking_outbox_write(booking=new_booking, event_type="booking.rescheduled")
        return new_booking


def _scheduling_booking_validate_booking_rules_for_reschedule(
    *,
    booking: Booking,
    time_slot,
    settings,
) -> None:
    """改期时校验新时段业务规则，排除被改期的原预约计数。

    Args:
        booking (Booking): 原预约。
        time_slot: 新固定时段。
        settings: ``TenantBookingSettings`` 实例。

    Raises:
        ValidationError: 违反业务规则。
    """
    from scheduling.services.booking import ACTIVE_BOOKING_STATUSES

    now = timezone.now()
    slot_start = time_slot.start
    if slot_start < now + timedelta(minutes=settings.min_advance_minutes):
        raise ValidationError("预约时间早于允许的最短提前预约时间。")
    if slot_start > now + timedelta(days=settings.max_booking_window_days):
        raise ValidationError("预约时间超出允许的最远可预约范围。")

    future_active_count = (
        Booking.objects.filter(
            customer=booking.customer,
            status__in=ACTIVE_BOOKING_STATUSES,
            time_slot__start__gt=now,
        )
        .exclude(pk=booking.pk)
        .count()
    )
    if future_active_count >= settings.future_booking_limit:
        raise ValidationError("您已达到未来有效预约数量上限。")


def scheduling_booking_party_size_update(
    *,
    booking: Booking,
    party_size: int,
) -> Booking:
    """客户修改预约人数；增加时校验容量，减少时立即释放。

    Args:
        booking (Booking): 目标预约。
        party_size (int): 新人数。

    Returns:
        Booking: 更新后的预约。

    Raises:
        ValidationError: 不可修改或容量不足。
    """
    from scheduling.services.booking_create import _scheduling_booking_remaining_capacity

    _scheduling_booking_ensure_customer_modifiable(booking=booking)
    _scheduling_booking_ensure_before_cancel_deadline(booking=booking)

    if party_size == booking.party_size:
        return booking

    if party_size > booking.party_size:
        delta = party_size - booking.party_size
        remaining = _scheduling_booking_remaining_capacity(time_slot=booking.time_slot)
        if remaining < delta:
            raise ValidationError("该时段容量不足。")

    booking.party_size = party_size
    booking.save(update_fields=["party_size", "updated_at"])
    return booking


def scheduling_booking_complete(*, booking: Booking) -> Booking:
    """管理员将预约标记为已完成。

    Args:
        booking (Booking): 目标预约。

    Returns:
        Booking: 更新后的预约。

    Raises:
        ValidationError: 当前状态不允许标记完成。
    """
    from scheduling.services.booking import ADMIN_COMPLETABLE_BOOKING_STATUSES

    if booking.status not in ADMIN_COMPLETABLE_BOOKING_STATUSES:
        raise ValidationError("当前预约状态不可标记为已完成。")

    booking.status = BookingStatus.COMPLETED
    booking.save(update_fields=["status", "updated_at"])
    return booking


def scheduling_booking_no_show(*, booking: Booking) -> Booking:
    """管理员将预约标记为爽约。

    Args:
        booking (Booking): 目标预约。

    Returns:
        Booking: 更新后的预约。

    Raises:
        ValidationError: 当前状态不允许标记爽约。
    """
    from scheduling.services.booking import ADMIN_COMPLETABLE_BOOKING_STATUSES

    if booking.status not in ADMIN_COMPLETABLE_BOOKING_STATUSES:
        raise ValidationError("当前预约状态不可标记为爽约。")

    booking.status = BookingStatus.NO_SHOW
    booking.save(update_fields=["status", "updated_at"])
    return booking


def scheduling_booking_contact_update(
    *,
    booking: Booking,
    contact_name: str,
    contact_phone: str,
    otp_code: str | None = None,
) -> Booking:
    """更新代他人预约的联系人信息；手机号变更需 OTP 验证。

    Args:
        booking (Booking): 目标预约。
        contact_name (str): 联系人姓名。
        contact_phone (str): 联系人手机号。
        otp_code (str | None): 新手机号 OTP；手机号未变时可省略。

    Returns:
        Booking: 更新后的预约。

    Raises:
        ValidationError: 不可修改或 OTP 无效。
    """
    from accounts.services.otp import customer_otp_verify

    _scheduling_booking_ensure_customer_modifiable(booking=booking)

    normalized_phone = contact_phone.strip()
    if normalized_phone and normalized_phone != booking.contact_phone:
        if not otp_code:
            raise ValidationError("修改联系人手机号需提供验证码。")
        customer_otp_verify(phone=normalized_phone, code=otp_code)

    booking.contact_name = contact_name.strip()
    booking.contact_phone = normalized_phone
    booking.save(update_fields=["contact_name", "contact_phone", "updated_at"])
    return booking
