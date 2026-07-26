from celery import shared_task
from notifications.services.outbox import outbox_publish_pending


@shared_task(name="notifications.publish_outbox_events")
def notifications_publish_outbox_events() -> int:
    """重试发布未投递的 Outbox 事件到 RabbitMQ。

    Returns:
        int: 本次成功发布的事件数量。
    """
    return outbox_publish_pending()


@shared_task(name="notifications.send_appointment_reminders")
def notifications_send_appointment_reminders() -> int:
    """为即将开始的已确认预约写入提醒 Outbox 事件。

    Returns:
        int: 新写入的提醒事件数量。
    """
    from datetime import timedelta

    from django.utils import timezone
    from scheduling.models import Booking, BookingStatus, TenantBookingSettings

    from notifications.models import Notification
    from notifications.services.booking_hooks import notifications_booking_outbox_write

    now = timezone.now()
    reminders_written = 0
    bookings = (
        Booking.objects.filter(status=BookingStatus.CONFIRMED, time_slot__start__gt=now)
        .select_related("tenant", "customer__user__customer_profile", "service", "time_slot")
        .iterator()
    )
    for booking in bookings:
        settings, _created = TenantBookingSettings.objects.get_or_create(tenant=booking.tenant)
        reminder_minutes = settings.reminder_minutes_before
        window_start = booking.time_slot.start - timedelta(minutes=reminder_minutes)
        if now < window_start:
            continue
        if now >= booking.time_slot.start:
            continue
        if Notification.objects.filter(
            booking=booking,
            notification_type="booking.reminder",
        ).exists():
            continue
        notifications_booking_outbox_write(booking=booking, event_type="booking.reminder")
        reminders_written += 1
    return reminders_written
