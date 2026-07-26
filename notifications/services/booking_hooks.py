"""预约相关 Outbox 事件写入。"""

from __future__ import annotations

from scheduling.models import Booking, BookingStatus

from notifications.services.outbox import outbox_event_write


def notifications_booking_outbox_write(*, booking: Booking, event_type: str) -> None:
    """为预约业务操作写入 Outbox 事件（须在业务事务内调用）。

    Args:
        booking (Booking): 目标预约。
        event_type (str): 事件类型，如 ``booking.confirmed``。
    """
    recipient_user_id = booking.customer.user_id
    phone = ""
    if hasattr(booking.customer.user, "customer_profile"):
        phone = booking.customer.user.customer_profile.phone

    title, body = _notifications_booking_message_for_event(
        event_type=event_type,
        booking=booking,
    )
    outbox_event_write(
        tenant=booking.tenant,
        event_type=event_type,
        aggregate_type="booking",
        aggregate_id=booking.id,
        payload={
            "tenant_id": booking.tenant_id,
            "booking_id": booking.id,
            "recipient_user_id": recipient_user_id,
            "title": title,
            "body": body,
            "phone": phone,
        },
    )


def notifications_booking_outbox_write_for_create(*, booking: Booking) -> None:
    """预约创建后写入合适的 Outbox 事件。

    Args:
        booking (Booking): 新建预约。
    """
    if booking.status == BookingStatus.CONFIRMED:
        notifications_booking_outbox_write(booking=booking, event_type="booking.confirmed")
    elif booking.status == BookingStatus.PENDING:
        notifications_booking_outbox_write(booking=booking, event_type="booking.created")


def _notifications_booking_message_for_event(
    *, event_type: str, booking: Booking
) -> tuple[str, str]:
    """生成预约通知标题与正文。

    Args:
        event_type (str): 事件类型。
        booking (Booking): 目标预约。

    Returns:
        tuple[str, str]: ``(title, body)``。
    """
    service_name = booking.service.name
    if event_type == "booking.confirmed":
        return "预约已确认", f"您的 {service_name} 预约已确认。"
    if event_type == "booking.created":
        return "预约已提交", f"您的 {service_name} 预约已提交，等待确认。"
    if event_type == "booking.cancelled":
        return "预约已取消", f"您的 {service_name} 预约已取消。"
    if event_type == "booking.rescheduled":
        return "预约已改期", f"您的 {service_name} 预约已成功改期。"
    if event_type == "booking.reminder":
        return "预约提醒", f"您有即将开始的 {service_name} 预约，请准时到场。"
    return "预约通知", f"您的 {service_name} 预约有更新。"
