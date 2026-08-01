"""QueueTicket 状态变更服务。"""

from __future__ import annotations

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from queuing.models import QueueTicket, QueueTicketStatus


def _queue_ticket_get_for_update(*, ticket_id: int) -> QueueTicket:
    """锁定并加载排队号。

    Args:
        ticket_id (int): 排队号 ID。

    Returns:
        QueueTicket: 排队号实例。

    Raises:
        ValidationError: 排队号不存在。
    """
    try:
        return QueueTicket.objects.select_for_update().select_related("stylist").get(pk=ticket_id)
    except QueueTicket.DoesNotExist as exc:
        raise ValidationError("排队号不存在。") from exc


def queue_ticket_call(*, ticket_id: int) -> QueueTicket:
    """管理员叫号。

    Args:
        ticket_id (int): 排队号 ID。

    Returns:
        QueueTicket: 更新后的排队号。

    Raises:
        ValidationError: 状态不允许叫号。
    """
    with transaction.atomic():
        ticket = _queue_ticket_get_for_update(ticket_id=ticket_id)
        if ticket.status != QueueTicketStatus.WAITING:
            raise ValidationError("只能叫号排队中的顾客。")
        ticket.status = QueueTicketStatus.CALLED
        ticket.called_at = timezone.now()
        ticket.save(update_fields=["status", "called_at", "updated_at"])
    return ticket


def queue_ticket_start(*, ticket_id: int) -> QueueTicket:
    """管理员确认顾客到场并开始服务。

    Args:
        ticket_id (int): 排队号 ID。

    Returns:
        QueueTicket: 更新后的排队号。

    Raises:
        ValidationError: 状态不允许开始服务。
    """
    with transaction.atomic():
        ticket = _queue_ticket_get_for_update(ticket_id=ticket_id)
        if ticket.status != QueueTicketStatus.CALLED:
            raise ValidationError("只能对已叫号的顾客开始服务。")
        ticket.status = QueueTicketStatus.SERVING
        ticket.serving_started_at = timezone.now()
        ticket.save(update_fields=["status", "serving_started_at", "updated_at"])
    return ticket


def queue_ticket_complete(*, ticket_id: int) -> QueueTicket:
    """管理员标记服务完成。

    Args:
        ticket_id (int): 排队号 ID。

    Returns:
        QueueTicket: 更新后的排队号。

    Raises:
        ValidationError: 状态不允许完成。
    """
    with transaction.atomic():
        ticket = _queue_ticket_get_for_update(ticket_id=ticket_id)
        if ticket.status != QueueTicketStatus.SERVING:
            raise ValidationError("只能完成服务中的排队号。")
        ticket.status = QueueTicketStatus.COMPLETED
        ticket.completed_at = timezone.now()
        ticket.save(update_fields=["status", "completed_at", "updated_at"])
    return ticket


def queue_ticket_cancel(
    *,
    ticket_id: int,
    cancel_reason: str = "",
    by_customer: bool = False,
) -> QueueTicket:
    """取消排队号。

    Args:
        ticket_id (int): 排队号 ID。
        cancel_reason (str): 取消原因。
        by_customer (bool): 是否为顾客自行取消。

    Returns:
        QueueTicket: 更新后的排队号。

    Raises:
        ValidationError: 状态不允许取消。
    """
    with transaction.atomic():
        ticket = _queue_ticket_get_for_update(ticket_id=ticket_id)
        if by_customer and ticket.status != QueueTicketStatus.WAITING:
            raise ValidationError("当前状态不可自行取消，请联系门店。")
        if ticket.status in {QueueTicketStatus.COMPLETED, QueueTicketStatus.CANCELLED}:
            raise ValidationError("该排队号已结束。")
        ticket.status = QueueTicketStatus.CANCELLED
        ticket.cancel_reason = cancel_reason.strip()
        ticket.cancelled_at = timezone.now()
        ticket.save(
            update_fields=["status", "cancel_reason", "cancelled_at", "updated_at"]
        )
    return ticket


def queue_ticket_move_to_tail(*, ticket_id: int) -> QueueTicket:
    """将已叫号顾客移到 waiting 队尾。

    Args:
        ticket_id (int): 排队号 ID。

    Returns:
        QueueTicket: 更新后的排队号。

    Raises:
        ValidationError: 状态不允许移队尾。
    """
    with transaction.atomic():
        ticket = _queue_ticket_get_for_update(ticket_id=ticket_id)
        if ticket.status != QueueTicketStatus.CALLED:
            raise ValidationError("只能将已叫号但未到场的顾客移到队尾。")
        last_position = (
            QueueTicket.objects.filter(
                stylist_id=ticket.stylist_id,
                queue_date=ticket.queue_date,
                status=QueueTicketStatus.WAITING,
            ).aggregate(max_position=Max("position"))["max_position"]
            or 0
        )
        ticket.status = QueueTicketStatus.WAITING
        ticket.position = last_position + 1
        ticket.called_at = None
        ticket.save(update_fields=["status", "position", "called_at", "updated_at"])
    return ticket
