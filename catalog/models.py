from django.db import models


class Location(models.Model):
    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="locations",
    )
    name = models.CharField(max_length=255)
    address = models.TextField(blank=True, default="")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "name"],
                name="unique_tenant_location_name",
            ),
        ]
        verbose_name = "服务地点"
        verbose_name_plural = "服务地点"

    def __str__(self) -> str:
        """返回 ``租户slug:名称`` 格式的标识。"""
        return f"{self.tenant.slug}:{self.name}"


class Service(models.Model):
    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="services",
    )
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, default="")
    duration_minutes = models.PositiveIntegerField()
    price_cents = models.PositiveIntegerField(default=0)
    currency = models.CharField(max_length=3, default="CNY")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    resources = models.ManyToManyField(
        "catalog.Resource",
        related_name="services",
        blank=True,
    )

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "name"],
                name="unique_tenant_service_name",
            ),
        ]
        verbose_name = "服务项目"
        verbose_name_plural = "服务项目"

    def __str__(self) -> str:
        """返回 ``租户slug:名称`` 格式的标识。"""
        return f"{self.tenant.slug}:{self.name}"


class Resource(models.Model):
    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="resources",
    )
    location = models.ForeignKey(
        Location,
        on_delete=models.CASCADE,
        related_name="resources",
    )
    name = models.CharField(max_length=255)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "location", "name"],
                name="unique_tenant_location_resource_name",
            ),
        ]
        verbose_name = "可预约资源"
        verbose_name_plural = "可预约资源"

    def __str__(self) -> str:
        """返回 ``租户slug:名称`` 格式的标识。"""
        return f"{self.tenant.slug}:{self.name}"


class CatalogBusinessReference(models.Model):
    """记录目录项被业务历史引用，用于禁止物理删除。"""

    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="catalog_business_references",
    )
    location = models.ForeignKey(
        Location,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="business_references",
    )
    service = models.ForeignKey(
        Service,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="business_references",
    )
    resource = models.ForeignKey(
        Resource,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="business_references",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "目录业务引用"
        verbose_name_plural = "目录业务引用"

    def __str__(self) -> str:
        """返回引用目标的简要标识。"""
        if self.location_id:
            return f"ref:location:{self.location_id}"
        if self.service_id:
            return f"ref:service:{self.service_id}"
        if self.resource_id:
            return f"ref:resource:{self.resource_id}"
        return f"ref:{self.pk}"
