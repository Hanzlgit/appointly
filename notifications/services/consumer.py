"""Outbox 消息消费者：订阅 RabbitMQ 并调用幂等消费逻辑。"""

from __future__ import annotations

import json
import logging
from typing import Any

from django.conf import settings

from notifications.services.consume import notifications_outbox_event_consume
from notifications.services.messaging import broker_message_clear, broker_message_list

logger = logging.getLogger(__name__)

OUTBOX_EXCHANGE_NAME = "appointly.outbox"
OUTBOX_QUEUE_NAME = "appointly.outbox.consumer"


def outbox_consumer_message_handle(*, message: dict[str, Any]) -> None:
    """处理单条 Outbox 消息并产生通知副作用。

    Args:
        message (dict[str, Any]): 含 event_id、event_type、payload 的消息体。
    """
    notifications_outbox_event_consume(
        event_id=message["event_id"],
        event_type=message["event_type"],
        payload=message["payload"],
    )


def outbox_consumer_process_mock_pending() -> int:
    """处理 Mock 代理中待消费消息（开发/测试用）。

    Returns:
        int: 成功处理的消息数量。
    """
    messages = broker_message_list()
    for message in messages:
        outbox_consumer_message_handle(message=message)
    broker_message_clear()
    return len(messages)


def outbox_consumer_run() -> None:
    """长期订阅 RabbitMQ Outbox exchange 并消费消息。

    Raises:
        ValueError: 当前配置的消息代理不是 rabbitmq。
    """
    broker_name = getattr(settings, "OUTBOX_MESSAGE_BROKER", "mock")
    if broker_name != "rabbitmq":
        raise ValueError(
            f"outbox_consumer_run 需要 OUTBOX_MESSAGE_BROKER=rabbitmq，当前为: {broker_name}"
        )

    from kombu import Connection, Consumer, Exchange, Queue

    broker_url = settings.CELERY_BROKER_URL
    exchange = Exchange(OUTBOX_EXCHANGE_NAME, type="topic", durable=True)
    queue = Queue(
        OUTBOX_QUEUE_NAME,
        exchange=exchange,
        routing_key="#",
        durable=True,
    )

    def _on_message(body: Any, message: Any) -> None:
        """Kombu 回调：解析消息并 ack/requeue。"""
        try:
            if isinstance(body, bytes | str):
                parsed_body = json.loads(body)
            elif isinstance(body, dict):
                parsed_body = body
            else:
                raise TypeError(f"不支持的 Outbox 消息类型: {type(body)!r}")
            outbox_consumer_message_handle(message=parsed_body)
            message.ack()
        except Exception:
            logger.exception(
                "outbox_consumer_message_failed event_id=%s",
                body.get("event_id") if isinstance(body, dict) else None,
            )
            message.reject(requeue=True)

    with (
        Connection(broker_url) as connection,
        Consumer(
            connection,
            queues=[queue],
            callbacks=[_on_message],
            accept=["json", "application/json", "raw"],
        ),
    ):
        logger.info(
            "outbox_consumer_started exchange=%s queue=%s",
            OUTBOX_EXCHANGE_NAME,
            OUTBOX_QUEUE_NAME,
        )
        while True:
            connection.drain_events()
