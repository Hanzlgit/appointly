from django.db import models


class Location(models.Model):
    """洗剪吹门店。"""

    name = models.CharField(max_length=255, unique=True)
    address = models.TextField(blank=True, default="")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "门店"
        verbose_name_plural = "门店"

    def __str__(self) -> str:
        """返回门店名称。"""
        return self.name


class StylistQueueStatus(models.TextChoices):
    """理发师当日接单状态。"""

    OPEN = "open", "开放"
    PAUSED = "paused", "暂停"
    CLOSED = "closed", "关闭"


class Stylist(models.Model):
    """理发师（原 Resource）。"""

    location = models.ForeignKey(
        Location,
        on_delete=models.CASCADE,
        related_name="stylists",
    )
    name = models.CharField(max_length=255)
    ticket_prefix = models.CharField(max_length=8, blank=True, default="")
    queue_status = models.CharField(
        max_length=16,
        choices=StylistQueueStatus.choices,
        default=StylistQueueStatus.OPEN,
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["location", "name"],
                name="unique_location_stylist_name",
            ),
        ]
        verbose_name = "理发师"
        verbose_name_plural = "理发师"

    def __str__(self) -> str:
        """返回 ``门店:名称`` 格式的标识。"""
        return f"{self.location.name}:{self.name}"


class Service(models.Model):
    """理发师提供的收费服务项目。"""

    stylist = models.ForeignKey(
        Stylist,
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

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["stylist", "name"],
                name="unique_stylist_service_name",
            ),
        ]
        verbose_name = "服务项目"
        verbose_name_plural = "服务项目"

    def __str__(self) -> str:
        """返回 ``理发师:服务名`` 格式的标识。"""
        return f"{self.stylist.name}:{self.name}"


class CatalogBusinessReference(models.Model):
    """记录目录项被业务历史引用，用于禁止物理删除。"""

    location = models.ForeignKey(
        Location,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="business_references",
    )
    stylist = models.ForeignKey(
        Stylist,
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
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "目录业务引用"
        verbose_name_plural = "目录业务引用"

    def __str__(self) -> str:
        """返回引用目标的简要标识。"""
        if self.location_id:
            return f"ref:location:{self.location_id}"
        if self.stylist_id:
            return f"ref:stylist:{self.stylist_id}"
        if self.service_id:
            return f"ref:service:{self.service_id}"
        return f"ref:{self.pk}"
