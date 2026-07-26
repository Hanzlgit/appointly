from scheduling.models import Booking, BookingStatus, TimeSlot

ACTIVE_BOOKING_STATUSES = {
    BookingStatus.PENDING,
    BookingStatus.CONFIRMED,
    BookingStatus.STARTED,
}

CUSTOMER_MODIFIABLE_BOOKING_STATUSES = {
    BookingStatus.PENDING,
    BookingStatus.CONFIRMED,
}

TERMINAL_BOOKING_STATUSES = {
    BookingStatus.CANCELLED,
    BookingStatus.RESCHEDULED,
    BookingStatus.EXPIRED,
    BookingStatus.REJECTED,
}


def scheduling_booking_has_active_on_slot(*, time_slot: TimeSlot) -> bool:
    """检查时段是否存在有效预约。

    Args:
        time_slot (TimeSlot): 固定时段。

    Returns:
        bool: 存在 PENDING 或 CONFIRMED 预约时返回 ``True``。
    """
    return Booking.objects.filter(
        time_slot=time_slot,
        status__in=ACTIVE_BOOKING_STATUSES,
    ).exists()


def scheduling_active_bookings_in_range(
    *,
    tenant_id: int,
    start,
    end,
    location_id: int | None = None,
    resource_id: int | None = None,
) -> list[Booking]:
    """查询时间范围内有有效预约的预约记录。

    Args:
        tenant_id (int): 租户 ID。
        start: 范围开始（UTC datetime）。
        end: 范围结束（UTC datetime）。
        location_id (int | None): 可选地点过滤。
        resource_id (int | None): 可选资源过滤。

    Returns:
        list[Booking]: 冲突的有效预约列表。
    """
    queryset = Booking.objects.filter(
        tenant_id=tenant_id,
        status__in=ACTIVE_BOOKING_STATUSES,
        time_slot__start__lt=end,
        time_slot__end__gt=start,
    ).select_related("time_slot")
    if location_id is not None:
        queryset = queryset.filter(time_slot__location_id=location_id)
    if resource_id is not None:
        queryset = queryset.filter(time_slot__resource_id=resource_id)
    return list(queryset)
