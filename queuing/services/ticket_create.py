"""QueueTicket 取号服务。"""

from __future__ import annotations

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from catalog.models import Service, Stylist, StylistQueueStatus
from queuing.models import ACTIVE_QUEUE_TICKET_STATUSES, QueueTicket, QueueTicketStatus


def queue_ticket_create(
    *,
    customer: User,
    stylist_id: int,
    service_id: int,
    idempotency_key: str,
) -> QueueTicket:
    """为顾客在指定理发师处取号排队。

    Args:
        customer (User): 取号顾客。
        stylist_id (int): 理发师 ID。
        service_id (int): 服务项目 ID。
        idempotency_key (str): 请求幂等键。

    Returns:
        QueueTicket: 新建或幂等重放的排队号。

    Raises:
        ValidationError: 校验失败或已有有效排队号。
    """
    existing = QueueTicket.objects.filter(
        customer=customer,
        idempotency_key=idempotency_key,
    ).first()
    if existing is not None:
        return existing

    if QueueTicket.objects.filter(
        customer=customer,
        status__in=ACTIVE_QUEUE_TICKET_STATUSES,
    ).exists():
        raise ValidationError("您已有进行中的排队，请先完成或取消后再取号。")

    try:
        stylist = Stylist.objects.select_related("location").get(
            id=stylist_id,
            is_active=True,
        )
    except Stylist.DoesNotExist as exc:
        raise ValidationError("理发师不存在或未启用。") from exc

    if stylist.queue_status != StylistQueueStatus.OPEN:
        raise ValidationError("该理发师当前暂停接单，请稍后再试。")

    try:
        service = Service.objects.get(
            id=service_id,
            stylist_id=stylist.id,
            is_active=True,
        )
    except Service.DoesNotExist as exc:
        raise ValidationError("服务项目不存在或未启用。") from exc

    queue_date = timezone.localdate()

    with transaction.atomic():
        stylist_locked = Stylist.objects.select_for_update().get(pk=stylist.pk)
        last_number = (
            QueueTicket.objects.filter(
                stylist=stylist_locked,
                queue_date=queue_date,
            ).aggregate(max_number=Max("ticket_number"))["max_number"]
            or 0
        )
        last_position = (
            QueueTicket.objects.filter(
                stylist=stylist_locked,
                queue_date=queue_date,
                status=QueueTicketStatus.WAITING,
            ).aggregate(max_position=Max("position"))["max_position"]
            or 0
        )
        ticket = QueueTicket.objects.create(
            location=stylist_locked.location,
            stylist=stylist_locked,
            service=service,
            customer=customer,
            ticket_number=last_number + 1,
            queue_date=queue_date,
            position=last_position + 1,
            status=QueueTicketStatus.WAITING,
            idempotency_key=idempotency_key,
        )
        from queuing.services.ticket_hooks import queue_ticket_outbox_created

        queue_ticket_outbox_created(ticket=ticket)

    return ticket
