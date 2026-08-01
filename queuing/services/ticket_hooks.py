"""QueueTicket Outbox 副作用。"""

from __future__ import annotations

from queuing.models import QueueTicket
from queuing.presenters import queue_ticket_to_dict
from queuing.selectors import queue_ticket_ahead_count, queue_ticket_estimated_wait_minutes


def queue_ticket_outbox_created(*, ticket: QueueTicket) -> None:
    """写入取号成功 Outbox 事件。

    Args:
        ticket (QueueTicket): 新建排队号。
    """
    from notifications.services.outbox import outbox_event_write

    ahead_count = queue_ticket_ahead_count(ticket=ticket)
    estimated_wait = queue_ticket_estimated_wait_minutes(ticket=ticket)
    display = queue_ticket_to_dict(ticket=ticket)["ticket_display"]
    phone = ""
    if hasattr(ticket.customer, "customer_profile"):
        phone = ticket.customer.customer_profile.phone

    outbox_event_write(
        event_type="queue.ticket.created",
        aggregate_type="queue_ticket",
        aggregate_id=ticket.id,
        payload={
            "recipient_user_id": ticket.customer_id,
            "queue_ticket_id": ticket.id,
            "phone": phone,
            "title": "取号成功",
            "body": (
                f"您已取号 {display}，"
                f"前面 {ahead_count} 人，预计等待 {estimated_wait} 分钟。"
            ),
        },
    )
