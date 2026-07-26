from tenants.models import Tenant

from scheduling.models import ScheduleRule, TimeSlot


def scheduling_schedule_rule_get_for_tenant(
    *,
    tenant: Tenant,
    rule_id: int,
) -> ScheduleRule:
    """按 ID 获取租户下的排班规则。

    Args:
        tenant (Tenant): 目标租户。
        rule_id (int): 规则 ID。

    Returns:
        ScheduleRule: 匹配的排班规则。

    Raises:
        ScheduleRule.DoesNotExist: 规则不存在。
    """
    return ScheduleRule.objects.select_related("location", "resource").get(
        tenant=tenant,
        id=rule_id,
    )


def scheduling_schedule_rule_list_for_tenant(*, tenant: Tenant) -> list[ScheduleRule]:
    """列出租户下全部排班规则。

    Args:
        tenant (Tenant): 目标租户。

    Returns:
        list[ScheduleRule]: 排班规则列表。
    """
    return list(
        ScheduleRule.objects.filter(tenant=tenant)
        .select_related("location", "resource")
        .order_by("id")
    )


def scheduling_time_slot_get_for_tenant(*, tenant: Tenant, time_slot_id: int) -> TimeSlot:
    """按 ID 获取租户下的固定时段。

    Args:
        tenant (Tenant): 目标租户。
        time_slot_id (int): 时段 ID。

    Returns:
        TimeSlot: 匹配的固定时段。

    Raises:
        TimeSlot.DoesNotExist: 时段不存在。
    """
    return TimeSlot.objects.select_related("location", "resource").get(
        tenant=tenant,
        id=time_slot_id,
    )


def scheduling_schedule_rule_to_dict(*, rule: ScheduleRule) -> dict:
    """将排班规则映射为 API 响应字典。

    Args:
        rule (ScheduleRule): 排班规则实例。

    Returns:
        dict: 含规则字段的响应字典。
    """
    return {
        "id": rule.id,
        "location_id": rule.location_id,
        "resource_id": rule.resource_id,
        "days_of_week": rule.days_of_week,
        "start_time": rule.start_time.isoformat(),
        "end_time": rule.end_time.isoformat(),
        "capacity": rule.capacity,
        "is_active": rule.is_active,
        "created_at": rule.created_at,
        "updated_at": rule.updated_at,
    }


def scheduling_time_slot_to_dict(*, time_slot: TimeSlot) -> dict:
    """将固定时段映射为 API 响应字典。

    Args:
        time_slot (TimeSlot): 固定时段实例。

    Returns:
        dict: 含时段字段的响应字典。
    """
    return {
        "id": time_slot.id,
        "location_id": time_slot.location_id,
        "resource_id": time_slot.resource_id,
        "schedule_rule_id": time_slot.schedule_rule_id,
        "start": time_slot.start,
        "end": time_slot.end,
        "capacity": time_slot.capacity,
        "status": time_slot.status,
        "created_at": time_slot.created_at,
        "updated_at": time_slot.updated_at,
    }
