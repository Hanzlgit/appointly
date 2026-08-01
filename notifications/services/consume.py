"""Outbox 事件消费与副作用处理。"""

from __future__ import annotations

import uuid
from typing import Any

from django.contrib.auth.models import User
from django.db import transaction

from notifications.models import ProcessedEvent
from notifications.services.notification import notification_create


def notifications_outbox_event_consume(
    *,
    event_id: str,
    event_type: str,
    payload: dict[str, Any],
) -> None:
    """按事件 ID 幂等消费 Outbox 消息并产生通知副作用。

    Args:
        event_id (str): 事件唯一 ID。
        event_type (str): 事件类型。
        payload (dict[str, Any]): 事件载荷。
    """
    parsed_event_id = uuid.UUID(event_id)
    if ProcessedEvent.objects.filter(event_id=parsed_event_id).exists():
        return

    with transaction.atomic():
        if ProcessedEvent.objects.filter(event_id=parsed_event_id).exists():
            return

        _notifications_handle_event(
            event_type=event_type,
            payload=payload,
            event_id=parsed_event_id,
        )
        ProcessedEvent.objects.create(event_id=parsed_event_id)


def _notifications_handle_event(
    *,
    event_type: str,
    payload: dict[str, Any],
    event_id: uuid.UUID,
) -> None:
    """根据事件类型创建站内通知并发送短信。

    Args:
        event_type (str): 事件类型。
        payload (dict[str, Any]): 事件载荷。
        event_id (uuid.UUID): 源 Outbox 事件 ID。
    """
    from accounts.services.sms import sms_adapter_get

    recipient_user_id = payload.get("recipient_user_id")
    if recipient_user_id is None:
        return

    recipient = User.objects.get(pk=recipient_user_id)
    queue_ticket = None
    queue_ticket_id = payload.get("queue_ticket_id")
    if queue_ticket_id is not None:
        from queuing.models import QueueTicket

        queue_ticket = QueueTicket.objects.filter(pk=queue_ticket_id).first()

    notification_create(
        recipient=recipient,
        notification_type=event_type,
        title=payload.get("title", ""),
        body=payload.get("body", ""),
        queue_ticket=queue_ticket,
        source_event_id=event_id,
    )

    phone = payload.get("phone")
    if phone:
        adapter = sms_adapter_get()
        adapter.send(to=phone, body=payload.get("body", ""))
