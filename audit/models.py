from django.conf import settings
from django.db import models


class AuditLog(models.Model):
    """不可变审计日志。"""

    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="audit_logs",
    )
    operator = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_logs",
    )
    request_id = models.CharField(max_length=64, blank=True, default="")
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    action = models.CharField(max_length=64)
    target_type = models.CharField(max_length=32)
    target_id = models.PositiveBigIntegerField()
    before_value = models.JSONField(default=dict)
    after_value = models.JSONField(default=dict)
    details = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["tenant", "created_at"]),
            models.Index(fields=["tenant", "action", "created_at"]),
        ]
        verbose_name = "审计日志"
        verbose_name_plural = "审计日志"

    def __str__(self) -> str:
        """返回审计条目简要标识。"""
        return f"{self.action}:{self.target_type}:{self.target_id}"
