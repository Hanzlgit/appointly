"""经营看板聚合查询。"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from django.core.cache import cache
from django.db.models import Count
from django.db.models.functions import TruncDate
from scheduling.models import Booking, BookingStatus, TimeSlot
from tenants.models import Tenant

from audit.constants import DASHBOARD_CACHE_TTL_SECONDS, DASHBOARD_TREND_DAYS


def _dashboard_parse_reference_date(*, tenant: Tenant, reference_date: str | None) -> date:
    """解析看板参考日期（租户本地）。

    Args:
        tenant (Tenant): 目标租户。
        reference_date (str | None): ISO 日期字符串。

    Returns:
        date: 租户本地参考日。
    """
    if reference_date:
        return date.fromisoformat(reference_date)
    tenant_tz = ZoneInfo(tenant.timezone)
    return datetime.now(tenant_tz).date()


def _dashboard_day_range(*, tenant: Tenant, day: date) -> tuple[datetime, datetime]:
    """返回租户本地某日的 UTC 起止时间。

    Args:
        tenant (Tenant): 目标租户。
        day (date): 租户本地日期。

    Returns:
        tuple[datetime, datetime]: ``(start_utc, end_utc)``。
    """
    tenant_tz = ZoneInfo(tenant.timezone)
    start = datetime.combine(day, datetime.min.time(), tzinfo=tenant_tz).astimezone(UTC)
    end = start + timedelta(days=1)
    return start, end


def _dashboard_cache_key(
    *,
    tenant_id: int,
    reference_date: date,
    location_id: int | None,
) -> str:
    """生成看板缓存键。

    Args:
        tenant_id (int): 租户 ID。
        reference_date (date): 参考日期。
        location_id (int | None): 地点过滤。

    Returns:
        str: Redis 缓存键。
    """
    location_part = location_id if location_id is not None else "all"
    return f"audit:dashboard:v2:{tenant_id}:{reference_date.isoformat()}:{location_part}"


def _dashboard_status_summary(*, queryset) -> dict:
    """按预约状态聚合计数。

    Args:
        queryset: 预约 QuerySet。

    Returns:
        dict: 各状态数量。
    """
    status_counts = queryset.values("status").annotate(count=Count("id"))
    status_map = {row["status"]: row["count"] for row in status_counts}
    return {
        "pending": status_map.get(BookingStatus.PENDING, 0),
        "confirmed": status_map.get(BookingStatus.CONFIRMED, 0),
        "completed": status_map.get(BookingStatus.COMPLETED, 0),
        "cancelled": status_map.get(BookingStatus.CANCELLED, 0),
        "no_show": status_map.get(BookingStatus.NO_SHOW, 0),
    }


def dashboard_summary_compute(
    *,
    tenant: Tenant,
    reference_date: date,
    location_id: int | None = None,
) -> dict:
    """计算租户经营看板汇总（无缓存）。

    Args:
        tenant (Tenant): 目标租户。
        reference_date (date): 参考日期（租户本地）。
        location_id (int | None): 可选地点过滤。

    Returns:
        dict: 看板汇总数据。
    """
    day_start, day_end = _dashboard_day_range(tenant=tenant, day=reference_date)
    bookings_today = Booking.objects.filter(
        tenant=tenant,
        time_slot__start__gte=day_start,
        time_slot__start__lt=day_end,
    )
    if location_id is not None:
        bookings_today = bookings_today.filter(time_slot__location_id=location_id)

    today_summary = _dashboard_status_summary(queryset=bookings_today)

    bookings_upcoming = Booking.objects.filter(
        tenant=tenant,
        time_slot__start__gte=day_start,
    )
    if location_id is not None:
        bookings_upcoming = bookings_upcoming.filter(time_slot__location_id=location_id)
    upcoming_summary = _dashboard_status_summary(queryset=bookings_upcoming)

    trend_start = day_start
    trend_end = day_start + timedelta(days=DASHBOARD_TREND_DAYS)
    trend_bookings = Booking.objects.filter(
        tenant=tenant,
        time_slot__start__gte=trend_start,
        time_slot__start__lt=trend_end,
    )
    if location_id is not None:
        trend_bookings = trend_bookings.filter(time_slot__location_id=location_id)

    tenant_tz = ZoneInfo(tenant.timezone)
    trend_rows = (
        trend_bookings.annotate(local_day=TruncDate("time_slot__start", tzinfo=tenant_tz))
        .values("local_day")
        .annotate(count=Count("id"))
        .order_by("local_day")
    )
    trend_map = {row["local_day"]: row["count"] for row in trend_rows}
    seven_day_trend = []
    for offset in range(7):
        day = reference_date + timedelta(days=offset)
        seven_day_trend.append({"date": day, "count": trend_map.get(day, 0)})

    location_bookings = Booking.objects.filter(
        tenant=tenant,
        time_slot__start__gte=day_start,
        time_slot__start__lt=trend_end,
    )
    if location_id is not None:
        location_bookings = location_bookings.filter(time_slot__location_id=location_id)
    location_rows = (
        location_bookings.values("time_slot__location_id", "time_slot__location__name")
        .annotate(count=Count("id"))
        .order_by("-count")
    )
    bookings_by_location = [
        {
            "location_id": row["time_slot__location_id"],
            "location_name": row["time_slot__location__name"],
            "count": row["count"],
        }
        for row in location_rows
    ]

    slots = TimeSlot.objects.filter(
        tenant=tenant,
        start__gte=day_start,
        start__lt=trend_end,
    )
    if location_id is not None:
        slots = slots.filter(location_id=location_id)

    slot_minutes = {}
    for slot in slots.select_related("resource"):
        duration = int((slot.end - slot.start).total_seconds() // 60)
        available = duration * slot.capacity
        slot_minutes.setdefault(
            slot.resource_id,
            {"resource_name": slot.resource.name, "available": 0, "booked": 0},
        )
        slot_minutes[slot.resource_id]["available"] += available

    active_statuses = [
        BookingStatus.PENDING,
        BookingStatus.CONFIRMED,
        BookingStatus.STARTED,
        BookingStatus.COMPLETED,
        BookingStatus.NO_SHOW,
    ]
    booked_minutes: dict[int, int] = {}
    booked_names: dict[int, str] = {}
    for booking in Booking.objects.filter(
        tenant=tenant,
        status__in=active_statuses,
        time_slot__start__gte=day_start,
        time_slot__start__lt=trend_end,
    ).select_related("time_slot", "time_slot__resource"):
        if location_id is not None and booking.time_slot.location_id != location_id:
            continue
        duration = int((booking.time_slot.end - booking.time_slot.start).total_seconds() // 60)
        resource_id = booking.time_slot.resource_id
        booked_minutes[resource_id] = booked_minutes.get(resource_id, 0) + duration
        booked_names[resource_id] = booking.time_slot.resource.name

    resource_utilization = []
    all_resource_ids = set(slot_minutes.keys()) | set(booked_minutes.keys())
    for resource_id in sorted(all_resource_ids):
        available = slot_minutes.get(resource_id, {}).get("available", 0)
        booked = booked_minutes.get(resource_id, 0)
        name = slot_minutes.get(resource_id, {}).get("resource_name") or booked_names.get(
            resource_id,
            "",
        )
        rate = round(booked / available, 4) if available > 0 else 0.0
        resource_utilization.append(
            {
                "resource_id": resource_id,
                "resource_name": name,
                "booked_minutes": booked,
                "available_minutes": available,
                "utilization_rate": rate,
            }
        )

    service_rows = (
        location_bookings.values("service_id", "service__name")
        .annotate(count=Count("id"))
        .order_by("-count")[:10]
    )
    popular_services = [
        {
            "service_id": row["service_id"],
            "service_name": row["service__name"],
            "count": row["count"],
        }
        for row in service_rows
    ]

    return {
        "reference_date": reference_date,
        "today_summary": today_summary,
        "upcoming_summary": upcoming_summary,
        "seven_day_trend": seven_day_trend,
        "bookings_by_location": bookings_by_location,
        "resource_utilization": resource_utilization,
        "popular_services": popular_services,
    }


def dashboard_summary_get(
    *,
    tenant: Tenant,
    reference_date: str | None = None,
    location_id: int | None = None,
) -> dict:
    """获取租户经营看板汇总（带短缓存）。

    Args:
        tenant (Tenant): 目标租户。
        reference_date (str | None): 参考日期 ISO 字符串。
        location_id (int | None): 可选地点过滤。

    Returns:
        dict: 看板汇总数据。
    """
    parsed_date = _dashboard_parse_reference_date(tenant=tenant, reference_date=reference_date)
    cache_key = _dashboard_cache_key(
        tenant_id=tenant.id,
        reference_date=parsed_date,
        location_id=location_id,
    )
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    result = dashboard_summary_compute(
        tenant=tenant,
        reference_date=parsed_date,
        location_id=location_id,
    )
    cache.set(cache_key, result, timeout=DASHBOARD_CACHE_TTL_SECONDS)
    return result
