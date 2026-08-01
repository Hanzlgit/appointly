"""QueueTicket 响应映射。"""

from queuing.models import QueueTicket
from queuing.selectors import queue_ticket_ahead_count, queue_ticket_estimated_wait_minutes


def queue_ticket_to_dict(*, ticket: QueueTicket) -> dict:
    """将排队号映射为 API 响应字典。

    Args:
        ticket (QueueTicket): 排队号实例。

    Returns:
        dict: 响应数据。
    """
    prefix = ticket.stylist.ticket_prefix or ""
    return {
        "id": ticket.id,
        "ticket_display": f"{prefix}{ticket.ticket_number:03d}",
        "ticket_number": ticket.ticket_number,
        "status": ticket.status,
        "position": ticket.position,
        "ahead_count": queue_ticket_ahead_count(ticket=ticket),
        "estimated_wait_minutes": queue_ticket_estimated_wait_minutes(ticket=ticket),
        "location_id": ticket.location_id,
        "location_name": ticket.location.name,
        "stylist_id": ticket.stylist_id,
        "stylist_name": ticket.stylist.name,
        "service_id": ticket.service_id,
        "service_name": ticket.service.name,
        "service_duration_minutes": ticket.service.duration_minutes,
        "service_price_cents": ticket.service.price_cents,
        "queue_date": ticket.queue_date,
        "created_at": ticket.created_at,
    }
