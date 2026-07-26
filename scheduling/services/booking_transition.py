"""预约状态机：确认、拒绝、过期等状态变更。"""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from tenants.models import Tenant

from scheduling.models import Booking, BookingStatus


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

    booking.status = BookingStatus.CONFIRMED
    booking.pending_expires_at = None
    booking.save(update_fields=["status", "pending_expires_at", "updated_at"])
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
