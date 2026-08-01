"""通知与 Outbox 相关常量。"""

DEFAULT_REMINDER_MINUTES_BEFORE = 60

REMINDER_MINUTES_BEFORE_MIN = 5
REMINDER_MINUTES_BEFORE_MAX = 7 * 24 * 60

DEFAULT_NOTIFICATION_PAGE_SIZE = 10
MAX_NOTIFICATION_PAGE_SIZE = 50

NOTIFICATION_TYPES = (
    "booking.created",
    "booking.confirmed",
    "booking.cancelled",
    "booking.rescheduled",
    "booking.reminder",
)
