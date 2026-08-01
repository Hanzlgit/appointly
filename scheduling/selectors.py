from collections import defaultdict
from datetime import datetime
from zoneinfo import ZoneInfo

from catalog.models import Resource, Service
from django.contrib.auth.models import User
from django.db.models import Sum
from tenants.models import Tenant, TenantRole

from scheduling.models import Booking, ScheduleRule, TimeSlot, TimeSlotStatus
from scheduling.services.booking import ACTIVE_BOOKING_STATUSES


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


def scheduling_schedule_rule_list_for_tenant(
    *,
    tenant: Tenant,
    resource_id: int | None = None,
) -> list[ScheduleRule]:
    """列出租户下排班规则，可按资源过滤。

    Args:
        tenant (Tenant): 目标租户。
        resource_id (int | None): 可选资源 ID 过滤。

    Returns:
        list[ScheduleRule]: 排班规则列表。
    """
    queryset = ScheduleRule.objects.filter(tenant=tenant).select_related("location", "resource")
    if resource_id is not None:
        queryset = queryset.filter(resource_id=resource_id)
    return list(queryset.order_by("id"))


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
        "slot_interval_minutes": rule.slot_interval_minutes,
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


def scheduling_datetime_to_tenant_iso(*, tenant: Tenant, dt: datetime) -> str:
    """将 UTC datetime 格式化为租户时区的 ISO 8601 字符串。

    Args:
        tenant (Tenant): 目标租户。
        dt (datetime): 待格式化的 datetime（aware）。

    Returns:
        str: 含时区偏移的 ISO 8601 字符串。
    """
    tenant_tz = ZoneInfo(tenant.timezone)
    return dt.astimezone(tenant_tz).isoformat()


def scheduling_timeslot_remaining_capacity(*, time_slot: TimeSlot) -> int:
    """计算固定时段的剩余可预约容量。

    Args:
        time_slot (TimeSlot): 固定时段。

    Returns:
        int: 剩余容量（不小于 0）。
    """
    used = (
        Booking.objects.filter(
            time_slot=time_slot,
            status__in=ACTIVE_BOOKING_STATUSES,
        ).aggregate(total=Sum("party_size"))["total"]
        or 0
    )
    return max(0, time_slot.capacity - used)


def scheduling_availability_slots_for_resource(
    *,
    tenant: Tenant,
    start: datetime,
    end: datetime,
    resource_id: int,
    location_id: int | None = None,
) -> list[dict]:
    """查询指定资源在范围内的可用固定时段。

    Args:
        tenant (Tenant): 目标租户。
        start (datetime): 查询范围开始（UTC）。
        end (datetime): 查询范围结束（UTC）。
        resource_id (int): 资源 ID。
        location_id (int | None): 可选地点过滤。

    Returns:
        list[dict]: 含剩余容量的时段字典列表。
    """
    resource = Resource.objects.filter(tenant=tenant, id=resource_id).only("is_active").first()
    if resource is None or not resource.is_active:
        return []

    queryset = TimeSlot.objects.filter(
        tenant=tenant,
        resource_id=resource_id,
        resource__is_active=True,
        status=TimeSlotStatus.OPEN,
        start__lt=end,
        end__gt=start,
    ).order_by("start")
    if location_id is not None:
        queryset = queryset.filter(location_id=location_id)

    slots: list[dict] = []
    for time_slot in queryset:
        remaining = scheduling_timeslot_remaining_capacity(time_slot=time_slot)
        if remaining <= 0:
            continue
        slots.append(
            {
                "time_slot_id": time_slot.id,
                "resource_id": time_slot.resource_id,
                "location_id": time_slot.location_id,
                "start": scheduling_datetime_to_tenant_iso(tenant=tenant, dt=time_slot.start),
                "end": scheduling_datetime_to_tenant_iso(tenant=tenant, dt=time_slot.end),
                "capacity": time_slot.capacity,
                "remaining_capacity": remaining,
            }
        )
    return slots


def scheduling_availability_aggregate(
    *,
    tenant: Tenant,
    start: datetime,
    end: datetime,
    service_id: int | None = None,
    location_id: int | None = None,
) -> list[dict]:
    """按服务、地点与时间聚合可用容量。

    Args:
        tenant (Tenant): 目标租户。
        start (datetime): 查询范围开始（UTC）。
        end (datetime): 查询范围结束（UTC）。
        service_id (int | None): 可选服务过滤。
        location_id (int | None): 可选地点过滤。

    Returns:
        list[dict]: 聚合后的可用容量条目列表。
    """
    queryset = (
        TimeSlot.objects.filter(
            tenant=tenant,
            resource__is_active=True,
            status=TimeSlotStatus.OPEN,
            start__lt=end,
            end__gt=start,
        )
        .select_related("resource")
        .order_by("start")
    )
    if location_id is not None:
        queryset = queryset.filter(location_id=location_id)

    service_resources: dict[int, set[int]] = {}
    services = Service.objects.filter(tenant=tenant, is_active=True).prefetch_related("resources")
    if service_id is not None:
        services = services.filter(id=service_id)
    for service in services:
        service_resources[service.id] = {
            resource.id for resource in service.resources.all() if resource.is_active
        }

    aggregates: dict[tuple[int, int, str, str], int] = defaultdict(int)
    for time_slot in queryset:
        remaining = scheduling_timeslot_remaining_capacity(time_slot=time_slot)
        if remaining <= 0:
            continue
        start_iso = scheduling_datetime_to_tenant_iso(tenant=tenant, dt=time_slot.start)
        end_iso = scheduling_datetime_to_tenant_iso(tenant=tenant, dt=time_slot.end)
        for svc_id, resource_ids in service_resources.items():
            if time_slot.resource_id not in resource_ids:
                continue
            key = (svc_id, time_slot.location_id, start_iso, end_iso)
            aggregates[key] += remaining

    return [
        {
            "service_id": svc_id,
            "location_id": loc_id,
            "start": start_iso,
            "end": end_iso,
            "remaining_capacity": remaining_total,
        }
        for (svc_id, loc_id, start_iso, end_iso), remaining_total in sorted(
            aggregates.items(),
            key=lambda item: (item[0][2], item[0][0], item[0][1]),
        )
    ]


def scheduling_booking_list_for_customer(
    *,
    tenant: Tenant,
    customer,
) -> list[Booking]:
    """列出客户在当前租户下的预约。

    Args:
        tenant (Tenant): 目标租户。
        customer: 租户客户档案 ``TenantCustomer``。

    Returns:
        list[Booking]: 预约列表，按创建时间倒序。
    """
    return list(
        Booking.objects.filter(tenant=tenant, customer=customer)
        .select_related("time_slot", "service", "time_slot__resource", "time_slot__location")
        .order_by("-created_at")
    )


def scheduling_booking_settings_to_dict(*, settings) -> dict:
    """将租户预约规则映射为 API 响应字典。

    Args:
        settings: ``TenantBookingSettings`` 实例。

    Returns:
        dict: 含规则字段的响应字典。
    """
    return {
        "min_advance_minutes": settings.min_advance_minutes,
        "max_booking_window_days": settings.max_booking_window_days,
        "pending_retention_minutes": settings.pending_retention_minutes,
        "cancel_deadline_minutes": settings.cancel_deadline_minutes,
        "future_booking_limit": settings.future_booking_limit,
        "confirmation_mode": settings.confirmation_mode,
        "updated_at": settings.updated_at,
    }


def scheduling_location_has_unfinished_references(*, tenant: Tenant, location_id: int) -> bool:
    """检查地点是否存在未完成的排班或预约引用。

    Args:
        tenant (Tenant): 目标租户。
        location_id (int): 地点 ID。

    Returns:
        bool: 存在排班规则、固定时段或有效预约时返回 ``True``。
    """
    if ScheduleRule.objects.filter(tenant=tenant, location_id=location_id).exists():
        return True
    if TimeSlot.objects.filter(tenant=tenant, location_id=location_id).exists():
        return True
    return Booking.objects.filter(
        tenant=tenant,
        status__in=ACTIVE_BOOKING_STATUSES,
        time_slot__location_id=location_id,
    ).exists()


def scheduling_phone_mask(*, phone: str) -> str:
    """对手机号中间四位脱敏。

    Args:
        phone (str): 原始手机号。

    Returns:
        str: 脱敏后的手机号；过短则原样返回。
    """
    normalized = phone.strip()
    if len(normalized) < 7:
        return normalized
    return f"{normalized[:3]}****{normalized[-4:]}"


def scheduling_booking_list_for_staff(
    *,
    tenant: Tenant,
    user: User,
    role: str,
) -> list[Booking]:
    """列出后台可见预约；租户成员均可查看本租户全部预约。

    Args:
        tenant (Tenant): 目标租户。
        user (User): 当前用户。
        role (str): 用户在租户下的角色。

    Returns:
        list[Booking]: 预约列表，按创建时间倒序。
    """
    del user, role
    queryset = Booking.objects.filter(tenant=tenant).select_related(
        "time_slot",
        "service",
        "time_slot__resource",
        "time_slot__location",
        "customer__user__customer_profile",
    )
    return list(queryset.order_by("-created_at"))


def scheduling_booking_phone_for_viewer(
    *,
    booking: Booking,
    role: str,
) -> tuple[str, str]:
    """按查看者角色返回客户手机号与联系人手机号。

    Args:
        booking (Booking): 预约实例。
        role (str): 查看者角色。

    Returns:
        tuple[str, str]: ``(customer_phone, contact_phone)``。
    """
    customer_phone = ""
    if hasattr(booking.customer.user, "customer_profile"):
        customer_phone = booking.customer.user.customer_profile.phone

    contact_phone = booking.contact_phone
    if not contact_phone:
        contact_phone = customer_phone

    if role in {TenantRole.TENANT_ADMIN, "platform_admin"}:
        return customer_phone, contact_phone

    return (
        scheduling_phone_mask(phone=customer_phone),
        scheduling_phone_mask(phone=contact_phone),
    )


def scheduling_booking_to_dict(
    *,
    tenant: Tenant,
    booking: Booking,
    viewer_role: str | None = None,
) -> dict:
    """将预约映射为 API 响应字典。

    Args:
        tenant (Tenant): 目标租户（用于时区格式化）。
        booking (Booking): 预约实例。
        viewer_role (str | None): 查看者角色，用于手机号脱敏。

    Returns:
        dict: 含预约字段的响应字典。
    """
    time_slot = booking.time_slot
    location = time_slot.location
    resource = time_slot.resource
    service = booking.service
    payload = {
        "id": booking.id,
        "status": booking.status,
        "party_size": booking.party_size,
        "contact_name": booking.contact_name,
        "service_id": booking.service_id,
        "service_name": service.name,
        "resource_id": time_slot.resource_id,
        "resource_name": resource.name,
        "resource_is_active": resource.is_active,
        "location_id": time_slot.location_id,
        "location_name": location.name,
        "location_address": location.address,
        "location_is_active": location.is_active,
        "time_slot_id": time_slot.id,
        "start": scheduling_datetime_to_tenant_iso(tenant=tenant, dt=time_slot.start),
        "end": scheduling_datetime_to_tenant_iso(tenant=tenant, dt=time_slot.end),
        "rescheduled_from_id": booking.rescheduled_from_id,
        "rescheduled_to_id": booking.rescheduled_to_id,
        "created_at": booking.created_at,
        "customer_id": booking.customer_id,
    }
    if viewer_role is None:
        payload["contact_phone"] = booking.contact_phone
        return payload

    customer_phone, contact_phone = scheduling_booking_phone_for_viewer(
        booking=booking,
        role=viewer_role,
    )
    payload["customer_phone"] = customer_phone
    payload["contact_phone"] = contact_phone
    return payload
