from django.db import models


class TimeSlotStatus(models.TextChoices):
    OPEN = "open", "开放"
    CLOSED = "closed", "已关闭"


class BookingStatus(models.TextChoices):
    PENDING = "pending", "待确认"
    CONFIRMED = "confirmed", "已确认"
    STARTED = "started", "已开始"
    COMPLETED = "completed", "已完成"
    NO_SHOW = "no_show", "爽约"
    CANCELLED = "cancelled", "已取消"
    RESCHEDULED = "rescheduled", "已改期"
    EXPIRED = "expired", "已过期"
    REJECTED = "rejected", "已拒绝"


class BookingCancelActor(models.TextChoices):
    CUSTOMER = "customer", "客户"
    ADMIN = "admin", "管理员"
    SYSTEM = "system", "系统"


class BookingConfirmationMode(models.TextChoices):
    AUTO = "auto", "自动确认"
    MANUAL = "manual", "人工确认"


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


class TenantBookingSettings(models.Model):
    """租户预约业务规则配置。"""

    tenant = models.OneToOneField(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="booking_settings",
    )
    min_advance_minutes = models.PositiveIntegerField(default=60)
    max_booking_window_days = models.PositiveIntegerField(default=30)
    pending_retention_minutes = models.PositiveIntegerField(default=30)
    cancel_deadline_minutes = models.PositiveIntegerField(default=120)
    future_booking_limit = models.PositiveIntegerField(default=5)
    confirmation_mode = models.CharField(
        max_length=16,
        choices=BookingConfirmationMode.choices,
        default=BookingConfirmationMode.AUTO,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "租户预约规则"
        verbose_name_plural = "租户预约规则"

    def __str__(self) -> str:
        """返回租户 slug 标识。"""
        return f"booking-settings:{self.tenant.slug}"


class Booking(models.Model):
    """客户预约记录。"""

    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="bookings",
    )
    customer = models.ForeignKey(
        "tenants.TenantCustomer",
        on_delete=models.CASCADE,
        related_name="bookings",
    )
    time_slot = models.ForeignKey(
        TimeSlot,
        on_delete=models.CASCADE,
        related_name="bookings",
    )
    service = models.ForeignKey(
        "catalog.Service",
        on_delete=models.PROTECT,
        related_name="bookings",
    )
    status = models.CharField(max_length=16, choices=BookingStatus.choices)
    party_size = models.PositiveIntegerField(default=1)
    contact_name = models.CharField(max_length=128, blank=True, default="")
    contact_phone = models.CharField(max_length=32, blank=True, default="")
    idempotency_key = models.CharField(max_length=128)
    pending_expires_at = models.DateTimeField(null=True, blank=True)
    cancel_actor = models.CharField(
        max_length=16,
        choices=BookingCancelActor.choices,
        null=True,
        blank=True,
    )
    cancel_reason = models.TextField(blank=True, default="")
    cancel_operator = models.ForeignKey(
        "auth.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="cancelled_bookings",
    )
    rescheduled_to = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="rescheduled_from_booking",
    )
    rescheduled_from = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="rescheduled_to_booking",
    )
    archived_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "customer", "idempotency_key"],
                name="unique_booking_idempotency_per_customer",
            ),
        ]
        verbose_name = "预约"
        verbose_name_plural = "预约"

    def __str__(self) -> str:
        """返回预约简要标识。"""
        return f"booking:{self.pk}@{self.status}"
