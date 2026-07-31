from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from catalog.models import Location, Resource
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from tenants.models import Tenant

from scheduling.constants import MAX_BOOKING_WINDOW_DAYS, SLOT_GENERATION_BUFFER_DAYS
from scheduling.models import ScheduleRule, TimeSlot, TimeSlotStatus
from scheduling.validation import scheduling_slot_times_in_window


def _local_slot_bounds(
    *,
    tenant: Tenant,
    slot_date: date,
    start_time: time,
    end_time: time,
) -> tuple[datetime, datetime]:
    """将租户本地日期与时间转为 UTC 起止 datetime。

    Args:
        tenant (Tenant): 目标租户。
        slot_date (date): 本地日期。
        start_time (time): 本地开始时间。
        end_time (time): 本地结束时间。

    Returns:
        tuple[datetime, datetime]: UTC 时区的开始与结束 datetime。
    """
    tenant_tz = ZoneInfo(tenant.timezone)
    local_start = datetime.combine(slot_date, start_time, tzinfo=tenant_tz)
    local_end = datetime.combine(slot_date, end_time, tzinfo=tenant_tz)
    return local_start.astimezone(UTC), local_end.astimezone(UTC)


def scheduling_resource_has_overlap(
    *,
    resource: Resource,
    start: datetime,
    end: datetime,
    exclude_time_slot_id: int | None = None,
) -> bool:
    """检查资源在指定时间区间是否与已有开放时段重叠。

    Args:
        resource (Resource): 可预约资源。
        start (datetime): 待检开始时间（UTC）。
        end (datetime): 待检结束时间（UTC）。
        exclude_time_slot_id (int | None): 更新时排除的时段 ID。

    Returns:
        bool: 存在重叠时返回 ``True``。
    """
    queryset = TimeSlot.objects.filter(
        resource=resource,
        status=TimeSlotStatus.OPEN,
        start__lt=end,
        end__gt=start,
    )
    if exclude_time_slot_id is not None:
        queryset = queryset.exclude(id=exclude_time_slot_id)
    return queryset.exists()


@transaction.atomic
def scheduling_timeslot_create(
    *,
    tenant: Tenant,
    location: Location,
    resource: Resource,
    start: datetime,
    end: datetime,
    capacity: int,
    schedule_rule: ScheduleRule | None = None,
) -> TimeSlot:
    """创建单个固定时段并校验资源重叠。

    Args:
        tenant (Tenant): 目标租户。
        location (Location): 服务地点。
        resource (Resource): 可预约资源。
        start (datetime): 开始时间（UTC）。
        end (datetime): 结束时间（UTC）。
        capacity (int): 时段容量。
        schedule_rule (ScheduleRule | None): 来源排班规则。

    Returns:
        TimeSlot: 新创建的时段。

    Raises:
        ValidationError: 时间无效、归属错误或存在重叠。
    """
    if location.tenant_id != tenant.id or resource.tenant_id != tenant.id:
        raise ValidationError("地点或资源不属于当前租户。")
    if start >= end:
        raise ValidationError("时段结束时间必须晚于开始时间。")
    if scheduling_resource_has_overlap(resource=resource, start=start, end=end):
        raise ValidationError("该资源在此时间段已有重叠的开放时段。")

    time_slot = TimeSlot(
        tenant=tenant,
        location=location,
        resource=resource,
        schedule_rule=schedule_rule,
        start=start,
        end=end,
        capacity=capacity,
        status=TimeSlotStatus.OPEN,
    )
    time_slot.full_clean()
    time_slot.save()
    return time_slot


@transaction.atomic
def scheduling_timeslot_close(*, tenant: Tenant, time_slot: TimeSlot) -> TimeSlot:
    """关闭单个空闲时段。

    Args:
        tenant (Tenant): 目标租户。
        time_slot (TimeSlot): 待关闭时段。

    Returns:
        TimeSlot: 关闭后的时段。

    Raises:
        ValidationError: 时段不属于租户或存在有效预约。
    """
    if time_slot.tenant_id != tenant.id:
        raise ValidationError("时段不属于当前租户。")
    if time_slot.status == TimeSlotStatus.CLOSED:
        return time_slot

    from scheduling.services.booking import scheduling_booking_has_active_on_slot

    if scheduling_booking_has_active_on_slot(time_slot=time_slot):
        raise ValidationError("时段存在有效预约，无法关闭。")

    time_slot.status = TimeSlotStatus.CLOSED
    time_slot.save(update_fields=["status", "updated_at"])
    return time_slot


def scheduling_generation_end_date(*, from_date: date) -> date:
    """计算时段批量生成的结束日期（含预约窗口与缓冲）。

    Args:
        from_date (date): 生成起点日期。

    Returns:
        date: 生成结束日期（含）。
    """
    return from_date + timedelta(days=MAX_BOOKING_WINDOW_DAYS + SLOT_GENERATION_BUFFER_DAYS)


@transaction.atomic
def scheduling_timeslots_generate_for_rule(
    *,
    tenant: Tenant,
    rule: ScheduleRule,
    from_date: date | None = None,
    to_date: date | None = None,
) -> int:
    """按排班规则批量生成未来固定时段。

    Args:
        tenant (Tenant): 目标租户。
        rule (ScheduleRule): 排班规则。
        from_date (date | None): 生成起点；默认今天（租户本地）。
        to_date (date | None): 生成终点；默认覆盖预约窗口与缓冲。

    Returns:
        int: 新创建的时段数量。
    """
    if rule.tenant_id != tenant.id or not rule.is_active:
        return 0

    tenant_tz = ZoneInfo(tenant.timezone)
    today_local = timezone.now().astimezone(tenant_tz).date()
    start_date = from_date or today_local
    end_date = to_date or scheduling_generation_end_date(from_date=start_date)
    allowed_weekdays = set(rule.days_of_week)
    created_count = 0

    current_date = start_date
    while current_date <= end_date:
        if current_date.weekday() in allowed_weekdays:
            slot_times = scheduling_slot_times_in_window(
                start_time=rule.start_time,
                end_time=rule.end_time,
                slot_interval_minutes=rule.slot_interval_minutes,
            )
            for slot_start_time, slot_end_time in slot_times:
                slot_start, slot_end = _local_slot_bounds(
                    tenant=tenant,
                    slot_date=current_date,
                    start_time=slot_start_time,
                    end_time=slot_end_time,
                )
                exists = TimeSlot.objects.filter(
                    resource=rule.resource,
                    start=slot_start,
                    end=slot_end,
                ).exists()
                if not exists and not scheduling_resource_has_overlap(
                    resource=rule.resource,
                    start=slot_start,
                    end=slot_end,
                ):
                    scheduling_timeslot_create(
                        tenant=tenant,
                        location=rule.location,
                        resource=rule.resource,
                        start=slot_start,
                        end=slot_end,
                        capacity=rule.capacity,
                        schedule_rule=rule,
                    )
                    created_count += 1
        current_date += timedelta(days=1)

    return created_count


@transaction.atomic
def scheduling_timeslots_generate_for_tenant(*, tenant: Tenant) -> int:
    """为租户下所有活跃排班规则批量生成时段。

    Args:
        tenant (Tenant): 目标租户。

    Returns:
        int: 新创建的时段总数。
    """
    total_created = 0
    for rule in ScheduleRule.objects.filter(tenant=tenant, is_active=True):
        total_created += scheduling_timeslots_generate_for_rule(tenant=tenant, rule=rule)
    return total_created
