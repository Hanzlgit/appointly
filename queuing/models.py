from django.conf import settings
from django.db import models


class QueueTicketStatus(models.TextChoices):
    """排队号生命周期状态。"""

    WAITING = "waiting", "排队中"
    CALLED = "called", "已叫号"
    SERVING = "serving", "服务中"
    COMPLETED = "completed", "已完成"
    CANCELLED = "cancelled", "已取消"


ACTIVE_QUEUE_TICKET_STATUSES = frozenset(
    {
        QueueTicketStatus.WAITING,
        QueueTicketStatus.CALLED,
        QueueTicketStatus.SERVING,
    }
)


class QueueTicket(models.Model):
    """顾客在指定理发师处的排队号。"""

    location = models.ForeignKey(
        "catalog.Location",
        on_delete=models.CASCADE,
        related_name="queue_tickets",
    )
    stylist = models.ForeignKey(
        "catalog.Stylist",
        on_delete=models.CASCADE,
        related_name="queue_tickets",
    )
    service = models.ForeignKey(
        "catalog.Service",
        on_delete=models.PROTECT,
        related_name="queue_tickets",
    )
    customer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="queue_tickets",
    )
    ticket_number = models.PositiveIntegerField()
    queue_date = models.DateField()
    position = models.PositiveIntegerField()
    status = models.CharField(max_length=16, choices=QueueTicketStatus.choices)
    idempotency_key = models.CharField(max_length=128)
    called_at = models.DateTimeField(null=True, blank=True)
    serving_started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancel_reason = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["position", "created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["stylist", "queue_date", "ticket_number"],
                name="unique_stylist_date_ticket_number",
            ),
            models.UniqueConstraint(
                fields=["customer", "idempotency_key"],
                name="unique_queue_ticket_idempotency_per_customer",
            ),
            models.UniqueConstraint(
                fields=["customer"],
                condition=models.Q(
                    status__in=[
                        QueueTicketStatus.WAITING,
                        QueueTicketStatus.CALLED,
                        QueueTicketStatus.SERVING,
                    ]
                ),
                name="unique_active_queue_ticket_per_customer",
            ),
        ]
        verbose_name = "排队号"
        verbose_name_plural = "排队号"

    def __str__(self) -> str:
        """返回排队号简要标识。"""
        prefix = self.stylist.ticket_prefix or ""
        return f"{prefix}{self.ticket_number:03d}@{self.status}"
