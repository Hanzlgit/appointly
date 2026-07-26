"""消息代理抽象与 Mock 实现。"""

from __future__ import annotations

import json
import logging
from typing import Protocol

from django.conf import settings

logger = logging.getLogger(__name__)

_PUBLISHED_MESSAGES: list[dict] = []


class MessageBroker(Protocol):
    def publish(self, *, routing_key: str, message: dict) -> None:
        """投递消息到代理。

        Args:
            routing_key (str): 路由键。
            message (dict): 消息体。
        """
        ...


class MockMessageBroker:
    """开发/测试环境使用的内存消息代理。"""

    def publish(self, *, routing_key: str, message: dict) -> None:
        """记录已投递消息供测试观察。

        Args:
            routing_key (str): 路由键。
            message (dict): 消息体。
        """
        payload = {"routing_key": routing_key, **message}
        _PUBLISHED_MESSAGES.append(payload)
        logger.info(
            "mock_broker_publish routing_key=%s event_id=%s",
            routing_key,
            message.get("event_id"),
        )


class RabbitMQMessageBroker:
    """通过 Kombu 向 RabbitMQ 投递 Outbox 消息。"""

    def publish(self, *, routing_key: str, message: dict) -> None:
        """向 Celery broker 对应的 RabbitMQ 发布消息。

        Args:
            routing_key (str): 路由键。
            message (dict): 消息体。
        """
        from kombu import Connection, Exchange, Producer

        broker_url = settings.CELERY_BROKER_URL
        exchange = Exchange("appointly.outbox", type="topic", durable=True)
        with Connection(broker_url) as connection:
            producer = Producer(connection)
            producer.publish(
                json.dumps(message),
                exchange=exchange,
                routing_key=routing_key,
                serializer="raw",
                content_type="application/json",
                delivery_mode=2,
            )


def message_broker_get() -> MessageBroker:
    """返回当前配置的消息代理实例。

    Returns:
        MessageBroker: 可用消息代理。
    """
    broker_name = getattr(settings, "OUTBOX_MESSAGE_BROKER", "mock")
    if broker_name == "mock":
        return MockMessageBroker()
    if broker_name == "rabbitmq":
        return RabbitMQMessageBroker()
    raise ValueError(f"不支持的消息代理: {broker_name}")


def broker_message_list() -> list[dict]:
    """返回 Mock 代理已投递消息列表（测试辅助）。

    Returns:
        list[dict]: 已投递消息副本。
    """
    return list(_PUBLISHED_MESSAGES)


def broker_message_clear() -> None:
    """清空 Mock 代理投递记录（测试辅助）。"""
    _PUBLISHED_MESSAGES.clear()
