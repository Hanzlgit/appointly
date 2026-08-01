"""通知与 Outbox 相关常量。"""

DEFAULT_NOTIFICATION_PAGE_SIZE = 10
MAX_NOTIFICATION_PAGE_SIZE = 50

NOTIFICATION_TYPES = (
    "queue.ticket.created",
    "queue.ticket.called",
    "queue.ticket.requeued",
    "queue.ticket.cancelled",
    "queue.ticket.completed",
)
