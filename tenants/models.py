from django.conf import settings
from django.db import models


class Tenant(models.Model):
    slug = models.SlugField(max_length=64, unique=True)
    name = models.CharField(max_length=255)
    timezone = models.CharField(max_length=64, default="Asia/Shanghai")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "租户"
        verbose_name_plural = "租户"

    def __str__(self) -> str:
        return self.name


class TenantRole(models.TextChoices):
    TENANT_ADMIN = "tenant_admin", "租户管理员"
    STAFF = "staff", "工作人员"


class TenantMembership(models.Model):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="memberships")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="tenant_memberships",
    )
    role = models.CharField(max_length=32, choices=TenantRole.choices)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "user"],
                name="unique_tenant_user_membership",
            ),
        ]
        verbose_name = "租户成员"
        verbose_name_plural = "租户成员"

    def __str__(self) -> str:
        return f"{self.user} @ {self.tenant} ({self.role})"


class TenantScopedRecord(models.Model):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="scoped_records")
    label = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "label"],
                name="unique_tenant_scoped_record_label",
            ),
        ]
        ordering = ["label"]

    def __str__(self) -> str:
        return f"{self.tenant.slug}:{self.label}"
