import uuid

from django.conf import settings
from django.db import models


class OutboxEvent(models.Model):
    """事务性 Outbox 事件，与业务操作同事务写入。"""

    event_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    event_type = models.CharField(max_length=64)
    aggregate_type = models.CharField(max_length=32)
    aggregate_id = models.PositiveBigIntegerField()
    payload = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    published_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["created_at"]
        indexes = [
            models.Index(fields=["published_at", "created_at"]),
        ]
        verbose_name = "Outbox 事件"
        verbose_name_plural = "Outbox 事件"

    def __str__(self) -> str:
        """返回事件简要标识。"""
        return f"{self.event_type}:{self.event_id}"


class ProcessedEvent(models.Model):
    """已消费事件登记，保证消费者幂等。"""

    event_id = models.UUIDField(unique=True)
    processed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "已处理事件"
        verbose_name_plural = "已处理事件"

    def __str__(self) -> str:
        """返回事件 ID。"""
        return str(self.event_id)


class Notification(models.Model):
    """用户站内通知。"""

    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notifications",
    )
    notification_type = models.CharField(max_length=64)
    title = models.CharField(max_length=255)
    body = models.TextField()
    queue_ticket = models.ForeignKey(
        "queuing.QueueTicket",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="notifications",
    )
    source_event_id = models.UUIDField(null=True, blank=True)
    read_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["recipient", "created_at"]),
        ]
        verbose_name = "站内通知"
        verbose_name_plural = "站内通知"

    def __str__(self) -> str:
        """返回通知简要标识。"""
        return f"{self.notification_type}:{self.pk}"
