from datetime import UTC, date

from catalog.models import Location, Resource
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone as django_timezone
from tenants.models import Tenant

from scheduling.models import Booking, ScheduleRule, TimeSlot, TimeSlotStatus
from scheduling.services.booking import (
    ACTIVE_BOOKING_STATUSES,
    scheduling_active_bookings_in_range,
)
from scheduling.services.time_slot import scheduling_timeslots_generate_for_rule
from scheduling.validation import scheduling_schedule_rule_window_validate


def _validate_schedule_rule_refs(
    *,
    tenant: Tenant,
    location_id: int,
    resource_id: int,
) -> tuple[Location, Resource]:
    """校验并返回排班规则关联的地点与资源。

    Args:
        tenant (Tenant): 目标租户。
        location_id (int): 地点 ID。
        resource_id (int): 资源 ID。

    Returns:
        tuple[Location, Resource]: 校验通过的地点与资源。

    Raises:
        ValidationError: 地点或资源不存在或不属于租户。
    """
    try:
        location = Location.objects.get(id=location_id, tenant=tenant)
    except Location.DoesNotExist as exc:
        raise ValidationError("服务地点不存在。") from exc
    try:
        resource = Resource.objects.get(id=resource_id, tenant=tenant)
    except Resource.DoesNotExist as exc:
        raise ValidationError("可预约资源不存在。") from exc
    return location, resource


@transaction.atomic
def scheduling_schedule_rule_create(
    *,
    tenant: Tenant,
    location_id: int,
    resource_id: int,
    days_of_week: list[int],
    start_time,
    end_time,
    capacity: int,
    slot_interval_minutes: int = 30,
) -> ScheduleRule:
    """创建周期排班规则。

    Args:
        tenant (Tenant): 目标租户。
        location_id (int): 服务地点 ID。
        resource_id (int): 资源 ID。
        days_of_week (list[int]): 生效星期（0=周一，6=周日）。
        start_time: 本地开始时间。
        end_time: 本地结束时间。
        capacity (int): 时段容量。
        slot_interval_minutes (int): 时段间隔（分钟）。

    Returns:
        ScheduleRule: 新创建的排班规则。

    Raises:
        ValidationError: 参数无效或关联实体不存在。
    """
    location, resource = _validate_schedule_rule_refs(
        tenant=tenant,
        location_id=location_id,
        resource_id=resource_id,
    )
    if not days_of_week:
        raise ValidationError("至少选择一个生效星期。")
    scheduling_schedule_rule_window_validate(
        start_time=start_time,
        end_time=end_time,
        slot_interval_minutes=slot_interval_minutes,
    )

    rule = ScheduleRule(
        tenant=tenant,
        location=location,
        resource=resource,
        days_of_week=sorted(set(days_of_week)),
        start_time=start_time,
        end_time=end_time,
        slot_interval_minutes=slot_interval_minutes,
        capacity=capacity,
    )
    rule.full_clean()
    rule.save()
    return rule


def scheduling_rule_has_active_bookings_from(
    *,
    tenant: Tenant,
    rule: ScheduleRule,
    effective_date: date,
) -> bool:
    """检查规则资源在生效日及之后是否存在有效预约。

    Args:
        tenant (Tenant): 目标租户。
        rule (ScheduleRule): 排班规则。
        effective_date (date): 生效日期（租户本地）。

    Returns:
        bool: 存在有效预约时返回 ``True``。
    """
    from zoneinfo import ZoneInfo

    tenant_tz = ZoneInfo(tenant.timezone)
    effective_start = django_timezone.datetime.combine(
        effective_date,
        django_timezone.datetime.min.time(),
        tzinfo=tenant_tz,
    ).astimezone(UTC)

    conflicts = scheduling_active_bookings_in_range(
        tenant_id=tenant.id,
        start=effective_start,
        end=django_timezone.datetime.max.replace(tzinfo=UTC),
        resource_id=rule.resource_id,
    )
    return len(conflicts) > 0


def scheduling_rule_has_active_bookings_on_rule_slots_from(
    *,
    tenant: Tenant,
    rule: ScheduleRule,
    effective_date: date,
) -> bool:
    """检查规则关联时段在生效日及之后是否存在有效预约。

    Args:
        tenant (Tenant): 目标租户。
        rule (ScheduleRule): 排班规则。
        effective_date (date): 生效日期（租户本地）。

    Returns:
        bool: 存在有效预约时返回 ``True``。
    """
    from zoneinfo import ZoneInfo

    tenant_tz = ZoneInfo(tenant.timezone)
    effective_start = django_timezone.datetime.combine(
        effective_date,
        django_timezone.datetime.min.time(),
        tzinfo=tenant_tz,
    ).astimezone(UTC)

    return Booking.objects.filter(
        tenant=tenant,
        status__in=ACTIVE_BOOKING_STATUSES,
        time_slot__schedule_rule=rule,
        time_slot__start__gte=effective_start,
    ).exists()


@transaction.atomic
def scheduling_schedule_rule_delete(
    *,
    tenant: Tenant,
    rule: ScheduleRule,
) -> None:
    """删除排班规则并关闭今日及之后的空闲时段。

    Args:
        tenant (Tenant): 目标租户。
        rule (ScheduleRule): 待删除规则。

    Raises:
        ValidationError: 规则不属于租户或今日及之后存在有效预约。
    """
    if rule.tenant_id != tenant.id:
        raise ValidationError("排班规则不属于当前租户。")

    from zoneinfo import ZoneInfo

    tenant_tz = ZoneInfo(tenant.timezone)
    today_local = django_timezone.now().astimezone(tenant_tz).date()

    if scheduling_rule_has_active_bookings_on_rule_slots_from(
        tenant=tenant,
        rule=rule,
        effective_date=today_local,
    ):
        raise ValidationError("今日及之后存在有效预约，无法删除规则。")

    scheduling_timeslots_close_idle_from(
        tenant=tenant,
        effective_date=today_local,
        schedule_rule=rule,
    )
    rule.delete()


@transaction.atomic
def scheduling_schedule_rule_update(
    *,
    tenant: Tenant,
    rule: ScheduleRule,
    effective_date: date,
    location_id: int | None = None,
    resource_id: int | None = None,
    days_of_week: list[int] | None = None,
    start_time=None,
    end_time=None,
    capacity: int | None = None,
    slot_interval_minutes: int | None = None,
    is_active: bool | None = None,
) -> ScheduleRule:
    """变更排班规则并在生效日重新生成时段。

    Args:
        tenant (Tenant): 目标租户。
        rule (ScheduleRule): 待更新规则。
        effective_date (date): 变更生效日期（租户本地）。
        location_id (int | None): 新地点 ID。
        resource_id (int | None): 新资源 ID。
        days_of_week (list[int] | None): 新生效星期。
        start_time: 新开始时间。
        end_time: 新结束时间。
        capacity (int | None): 新容量。
        slot_interval_minutes (int | None): 新时段间隔（分钟）。
        is_active (bool | None): 启用状态。

    Returns:
        ScheduleRule: 更新后的规则。

    Raises:
        ValidationError: 生效日无效或存在冲突预约。
    """
    if rule.tenant_id != tenant.id:
        raise ValidationError("排班规则不属于当前租户。")
    if scheduling_rule_has_active_bookings_from(
        tenant=tenant,
        rule=rule,
        effective_date=effective_date,
    ):
        raise ValidationError("生效日及之后存在有效预约，无法变更规则。")

    if location_id is not None or resource_id is not None:
        location, resource = _validate_schedule_rule_refs(
            tenant=tenant,
            location_id=location_id or rule.location_id,
            resource_id=resource_id or rule.resource_id,
        )
        rule.location = location
        rule.resource = resource

    if days_of_week is not None:
        if not days_of_week:
            raise ValidationError("至少选择一个生效星期。")
        rule.days_of_week = sorted(set(days_of_week))
    if start_time is not None:
        rule.start_time = start_time
    if end_time is not None:
        rule.end_time = end_time
    if capacity is not None:
        rule.capacity = capacity
    if slot_interval_minutes is not None:
        rule.slot_interval_minutes = slot_interval_minutes
    if is_active is not None:
        rule.is_active = is_active

    scheduling_schedule_rule_window_validate(
        start_time=rule.start_time,
        end_time=rule.end_time,
        slot_interval_minutes=rule.slot_interval_minutes,
    )

    rule.full_clean()
    rule.save()

    scheduling_timeslots_close_idle_from(
        tenant=tenant,
        effective_date=effective_date,
        schedule_rule=rule,
    )
    scheduling_timeslots_generate_for_rule(
        tenant=tenant,
        rule=rule,
        from_date=effective_date,
    )
    return rule


@transaction.atomic
def scheduling_timeslots_close_idle_from(
    *,
    tenant: Tenant,
    effective_date: date,
    schedule_rule: ScheduleRule | None = None,
    location_id: int | None = None,
    resource_id: int | None = None,
) -> int:
    """批量关闭生效日及之后的空闲时段。

    Args:
        tenant (Tenant): 目标租户。
        effective_date (date): 生效日期（租户本地）。
        schedule_rule (ScheduleRule | None): 限定规则来源。
        location_id (int | None): 可选地点过滤。
        resource_id (int | None): 可选资源过滤。

    Returns:
        int: 关闭的时段数量。
    """
    from zoneinfo import ZoneInfo

    tenant_tz = ZoneInfo(tenant.timezone)
    effective_start = django_timezone.datetime.combine(
        effective_date,
        django_timezone.datetime.min.time(),
        tzinfo=tenant_tz,
    ).astimezone(UTC)

    queryset = TimeSlot.objects.filter(
        tenant=tenant,
        status=TimeSlotStatus.OPEN,
        start__gte=effective_start,
    )
    if schedule_rule is not None:
        queryset = queryset.filter(schedule_rule=schedule_rule)
    if location_id is not None:
        queryset = queryset.filter(location_id=location_id)
    if resource_id is not None:
        queryset = queryset.filter(resource_id=resource_id)

    closed_count = 0
    for time_slot in queryset:
        from scheduling.services.booking import scheduling_booking_has_active_on_slot

        if not scheduling_booking_has_active_on_slot(time_slot=time_slot):
            time_slot.status = TimeSlotStatus.CLOSED
            time_slot.save(update_fields=["status", "updated_at"])
            closed_count += 1
    return closed_count


@transaction.atomic
def scheduling_timeslots_batch_close(
    *,
    tenant: Tenant,
    start,
    end,
    location_id: int | None = None,
    resource_id: int | None = None,
) -> int:
    """按范围批量关闭空闲时段；存在有效预约时拒绝。

    Args:
        tenant (Tenant): 目标租户。
        start: 范围开始（UTC datetime）。
        end: 范围结束（UTC datetime）。
        location_id (int | None): 可选地点过滤。
        resource_id (int | None): 可选资源过滤。

    Returns:
        int: 关闭的时段数量。

    Raises:
        ValidationError: 范围内存在有效预约。
    """
    conflicts = scheduling_active_bookings_in_range(
        tenant_id=tenant.id,
        start=start,
        end=end,
        location_id=location_id,
        resource_id=resource_id,
    )
    if conflicts:
        conflict_ids = [booking.id for booking in conflicts]
        raise ValidationError(
            "范围内存在有效预约，无法批量关闭。",
            params={"conflicts": conflict_ids},
        )

    queryset = TimeSlot.objects.filter(
        tenant=tenant,
        status=TimeSlotStatus.OPEN,
        start__lt=end,
        end__gt=start,
    )
    if location_id is not None:
        queryset = queryset.filter(location_id=location_id)
    if resource_id is not None:
        queryset = queryset.filter(resource_id=resource_id)

    closed_count = 0
    for time_slot in queryset:
        time_slot.status = TimeSlotStatus.CLOSED
        time_slot.save(update_fields=["status", "updated_at"])
        closed_count += 1
    return closed_count
