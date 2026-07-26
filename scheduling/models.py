from django.db import models


class TimeSlotStatus(models.TextChoices):
    OPEN = "open", "开放"
    CLOSED = "closed", "已关闭"


class BookingStatus(models.TextChoices):
    PENDING = "pending", "待确认"
    CONFIRMED = "confirmed", "已确认"
    CANCELLED = "cancelled", "已取消"


class ScheduleRule(models.Model):
    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="schedule_rules",
    )
    location = models.ForeignKey(
        "catalog.Location",
        on_delete=models.CASCADE,
        related_name="schedule_rules",
    )
    resource = models.ForeignKey(
        "catalog.Resource",
        on_delete=models.CASCADE,
        related_name="schedule_rules",
    )
    days_of_week = models.JSONField(default=list)
    start_time = models.TimeField()
    end_time = models.TimeField()
    capacity = models.PositiveIntegerField(default=1)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["id"]
        verbose_name = "周期排班规则"
        verbose_name_plural = "周期排班规则"

    def __str__(self) -> str:
        """返回规则简要标识。"""
        return f"rule:{self.pk}@{self.tenant.slug}"


class TimeSlot(models.Model):
    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="time_slots",
    )
    location = models.ForeignKey(
        "catalog.Location",
        on_delete=models.CASCADE,
        related_name="time_slots",
    )
    resource = models.ForeignKey(
        "catalog.Resource",
        on_delete=models.CASCADE,
        related_name="time_slots",
    )
    schedule_rule = models.ForeignKey(
        ScheduleRule,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="time_slots",
    )
    start = models.DateTimeField()
    end = models.DateTimeField()
    capacity = models.PositiveIntegerField(default=1)
    status = models.CharField(
        max_length=16,
        choices=TimeSlotStatus.choices,
        default=TimeSlotStatus.OPEN,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["start"]
        constraints = [
            models.UniqueConstraint(
                fields=["resource", "start", "end"],
                name="unique_resource_timeslot_start_end",
            ),
        ]
        verbose_name = "固定时段"
        verbose_name_plural = "固定时段"

    def __str__(self) -> str:
        """返回时段简要标识。"""
        return f"slot:{self.pk}@{self.resource_id}"


class Booking(models.Model):
    """最小预约模型，供排班冲突检测使用。"""

    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="bookings",
    )
    time_slot = models.ForeignKey(
        TimeSlot,
        on_delete=models.CASCADE,
        related_name="bookings",
    )
    status = models.CharField(max_length=16, choices=BookingStatus.choices)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "预约"
        verbose_name_plural = "预约"

    def __str__(self) -> str:
        """返回预约简要标识。"""
        return f"booking:{self.pk}@{self.status}"
