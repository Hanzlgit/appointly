"""Outbox 事件写入与发布。"""

from __future__ import annotations

import uuid
from typing import Any

from django.utils import timezone

from notifications.models import OutboxEvent
from notifications.services.messaging import message_broker_get


def outbox_event_write(
    *,
    event_type: str,
    aggregate_type: str,
    aggregate_id: int,
    payload: dict[str, Any],
    event_id: uuid.UUID | None = None,
) -> OutboxEvent:
    """在当前数据库事务中写入 Outbox 事件。

    Args:
        event_type (str): 事件类型。
        aggregate_type (str): 聚合根类型。
        aggregate_id (int): 聚合根 ID。
        payload (dict[str, Any]): 事件载荷。
        event_id (uuid.UUID | None): 可选固定事件 ID。

    Returns:
        OutboxEvent: 新建的事件记录。
    """
    return OutboxEvent.objects.create(
        event_id=event_id or uuid.uuid4(),
        event_type=event_type,
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        payload=payload,
    )


def outbox_publish_pending(*, batch_size: int = 100) -> int:
    """发布未投递的 Outbox 事件到消息代理。

    Args:
        batch_size (int): 单次处理上限。

    Returns:
        int: 成功发布的事件数量。
    """
    broker = message_broker_get()
    unpublished = list(
        OutboxEvent.objects.filter(published_at__isnull=True).order_by("created_at")[:batch_size]
    )
    published_count = 0
    now = timezone.now()
    for event in unpublished:
        message = {
            "event_id": str(event.event_id),
            "event_type": event.event_type,
            "payload": event.payload,
        }
        broker.publish(routing_key=event.event_type, message=message)
        event.published_at = now
        event.save(update_fields=["published_at"])
        published_count += 1
    return published_count
