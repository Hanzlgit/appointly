"""排队指标查询。"""

from __future__ import annotations

from django.contrib.auth.models import User
from django.db.models import Q, QuerySet

from catalog.models import Service
from queuing.models import ACTIVE_QUEUE_TICKET_STATUSES, QueueTicket, QueueTicketStatus


def queue_ticket_get(*, ticket_id: int) -> QueueTicket | None:
    """按 ID 查询排队号。

    Args:
        ticket_id (int): 排队号 ID。

    Returns:
        QueueTicket | None: 排队号实例；不存在时返回 ``None``。
    """
    return (
        QueueTicket.objects.filter(pk=ticket_id)
        .select_related("location", "stylist", "service", "customer")
        .first()
    )


def queue_ticket_mine(*, customer: User) -> QueueTicket | None:
    """查询顾客当前有效排队号。

    Args:
        customer (User): 顾客用户。

    Returns:
        QueueTicket | None: 有效排队号；无则 ``None``。
    """
    return (
        QueueTicket.objects.filter(
            customer=customer,
            status__in=ACTIVE_QUEUE_TICKET_STATUSES,
        )
        .select_related("location", "stylist", "service")
        .order_by("-created_at")
        .first()
    )


def queue_ticket_ahead_count(*, ticket: QueueTicket) -> int:
    """计算指定排队号前面还有多少 waiting 顾客。

    Args:
        ticket (QueueTicket): 目标排队号。

    Returns:
        int: 前方 waiting 人数。
    """
    if ticket.status != QueueTicketStatus.WAITING:
        return 0
    return QueueTicket.objects.filter(
        stylist_id=ticket.stylist_id,
        queue_date=ticket.queue_date,
        status=QueueTicketStatus.WAITING,
        position__lt=ticket.position,
    ).count()


def queue_ticket_estimated_wait_minutes(*, ticket: QueueTicket) -> int:
    """估算预计等待分钟数。

    前方 waiting 号的服务时长之和，加上当前 serving 号的服务时长（简化版）。

    Args:
        ticket (QueueTicket): 目标排队号。

    Returns:
        int: 预计等待分钟数。
    """
    if ticket.status not in {QueueTicketStatus.WAITING, QueueTicketStatus.CALLED}:
        return 0

    ahead_tickets = QueueTicket.objects.filter(
        stylist_id=ticket.stylist_id,
        queue_date=ticket.queue_date,
        status=QueueTicketStatus.WAITING,
        position__lt=ticket.position,
    ).select_related("service")
    ahead_minutes = sum(t.service.duration_minutes for t in ahead_tickets)

    serving = (
        QueueTicket.objects.filter(
            stylist_id=ticket.stylist_id,
            queue_date=ticket.queue_date,
            status=QueueTicketStatus.SERVING,
        )
        .select_related("service")
        .first()
    )
    serving_minutes = serving.service.duration_minutes if serving else 0
    return ahead_minutes + serving_minutes


def queue_ticket_list_for_stylist(
    *,
    stylist_id: int,
    queue_date,
    status: str | None = None,
    search: str = "",
) -> QuerySet[QueueTicket]:
    """查询理发师某日排队列表。

    Args:
        stylist_id (int): 理发师 ID。
        queue_date: 排队日期。
        status (str | None): 可选状态筛选。
        search (str): 号段或手机号模糊搜索。

    Returns:
        QuerySet[QueueTicket]: 排队号查询集。
    """
    queryset = (
        QueueTicket.objects.filter(stylist_id=stylist_id, queue_date=queue_date)
        .select_related("service", "customer", "customer__customer_profile")
        .order_by("position", "created_at")
    )
    if status:
        queryset = queryset.filter(status=status)
    if search.strip():
        term = search.strip()
        queryset = queryset.filter(
            Q(customer__customer_profile__phone__icontains=term)
            | Q(ticket_number__icontains=term)
        )
    return queryset
