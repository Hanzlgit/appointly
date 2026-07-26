"""租户预约业务规则读写与校验。"""

from __future__ import annotations

from django.core.exceptions import ValidationError
from notifications.constants import DEFAULT_REMINDER_MINUTES_BEFORE
from tenants.models import Tenant

from scheduling.constants import (
    CANCEL_DEADLINE_MINUTES_MAX,
    CANCEL_DEADLINE_MINUTES_MIN,
    DEFAULT_CANCEL_DEADLINE_MINUTES,
    DEFAULT_CONFIRMATION_MODE,
    DEFAULT_FUTURE_BOOKING_LIMIT,
    DEFAULT_MAX_BOOKING_WINDOW_DAYS,
    DEFAULT_MIN_ADVANCE_MINUTES,
    DEFAULT_PENDING_RETENTION_MINUTES,
    FUTURE_BOOKING_LIMIT_MAX,
    FUTURE_BOOKING_LIMIT_MIN,
    MAX_BOOKING_WINDOW_DAYS_MAX,
    MAX_BOOKING_WINDOW_DAYS_MIN,
    MIN_ADVANCE_MINUTES_MAX,
    MIN_ADVANCE_MINUTES_MIN,
    PENDING_RETENTION_MINUTES_MAX,
    PENDING_RETENTION_MINUTES_MIN,
    BookingConfirmationMode,
)
from scheduling.models import TenantBookingSettings


def scheduling_booking_settings_get_for_tenant(*, tenant: Tenant) -> TenantBookingSettings:
    """获取租户预约规则，不存在时返回带默认值的未持久化实例。

    Args:
        tenant (Tenant): 目标租户。

    Returns:
        TenantBookingSettings: 租户预约规则实例。
    """
    settings, _created = TenantBookingSettings.objects.get_or_create(
        tenant=tenant,
        defaults={
            "min_advance_minutes": DEFAULT_MIN_ADVANCE_MINUTES,
            "max_booking_window_days": DEFAULT_MAX_BOOKING_WINDOW_DAYS,
            "pending_retention_minutes": DEFAULT_PENDING_RETENTION_MINUTES,
            "cancel_deadline_minutes": DEFAULT_CANCEL_DEADLINE_MINUTES,
            "future_booking_limit": DEFAULT_FUTURE_BOOKING_LIMIT,
            "confirmation_mode": DEFAULT_CONFIRMATION_MODE,
            "reminder_minutes_before": DEFAULT_REMINDER_MINUTES_BEFORE,
        },
    )
    return settings


def scheduling_booking_settings_update(
    *,
    tenant: Tenant,
    min_advance_minutes: int | None = None,
    max_booking_window_days: int | None = None,
    pending_retention_minutes: int | None = None,
    cancel_deadline_minutes: int | None = None,
    future_booking_limit: int | None = None,
    confirmation_mode: str | None = None,
) -> TenantBookingSettings:
    """更新租户预约业务规则并校验平台上下限。

    Args:
        tenant (Tenant): 目标租户。
        min_advance_minutes (int | None): 最短提前预约分钟数。
        max_booking_window_days (int | None): 最远可预约天数。
        pending_retention_minutes (int | None): 待确认保留分钟数。
        cancel_deadline_minutes (int | None): 最晚取消截止分钟数。
        future_booking_limit (int | None): 客户未来有效预约上限。
        confirmation_mode (str | None): 确认模式 ``auto`` 或 ``manual``。

    Returns:
        TenantBookingSettings: 更新后的规则实例。

    Raises:
        ValidationError: 配置值超出平台允许范围或确认模式无效。
    """
    settings = scheduling_booking_settings_get_for_tenant(tenant=tenant)
    updates: dict[str, int | str] = {}

    if min_advance_minutes is not None:
        _scheduling_booking_settings_validate_range(
            field_name="min_advance_minutes",
            value=min_advance_minutes,
            minimum=MIN_ADVANCE_MINUTES_MIN,
            maximum=MIN_ADVANCE_MINUTES_MAX,
        )
        updates["min_advance_minutes"] = min_advance_minutes
    if max_booking_window_days is not None:
        _scheduling_booking_settings_validate_range(
            field_name="max_booking_window_days",
            value=max_booking_window_days,
            minimum=MAX_BOOKING_WINDOW_DAYS_MIN,
            maximum=MAX_BOOKING_WINDOW_DAYS_MAX,
        )
        updates["max_booking_window_days"] = max_booking_window_days
    if pending_retention_minutes is not None:
        _scheduling_booking_settings_validate_range(
            field_name="pending_retention_minutes",
            value=pending_retention_minutes,
            minimum=PENDING_RETENTION_MINUTES_MIN,
            maximum=PENDING_RETENTION_MINUTES_MAX,
        )
        updates["pending_retention_minutes"] = pending_retention_minutes
    if cancel_deadline_minutes is not None:
        _scheduling_booking_settings_validate_range(
            field_name="cancel_deadline_minutes",
            value=cancel_deadline_minutes,
            minimum=CANCEL_DEADLINE_MINUTES_MIN,
            maximum=CANCEL_DEADLINE_MINUTES_MAX,
        )
        updates["cancel_deadline_minutes"] = cancel_deadline_minutes
    if future_booking_limit is not None:
        _scheduling_booking_settings_validate_range(
            field_name="future_booking_limit",
            value=future_booking_limit,
            minimum=FUTURE_BOOKING_LIMIT_MIN,
            maximum=FUTURE_BOOKING_LIMIT_MAX,
        )
        updates["future_booking_limit"] = future_booking_limit
    if confirmation_mode is not None:
        valid_modes = {BookingConfirmationMode.AUTO, BookingConfirmationMode.MANUAL}
        if confirmation_mode not in valid_modes:
            raise ValidationError("confirmation_mode 必须为 auto 或 manual。")
        updates["confirmation_mode"] = confirmation_mode

    if updates:
        for field_name, value in updates.items():
            setattr(settings, field_name, value)
        settings.save(update_fields=[*updates.keys(), "updated_at"])

    return settings


def _scheduling_booking_settings_validate_range(
    *,
    field_name: str,
    value: int,
    minimum: int,
    maximum: int,
) -> None:
    """校验单个配置项是否在平台允许范围内。

    Args:
        field_name (str): 字段名。
        value (int): 待校验值。
        minimum (int): 平台下限。
        maximum (int): 平台上限。

    Raises:
        ValidationError: 值超出范围。
    """
    if value < minimum or value > maximum:
        raise ValidationError(f"{field_name} 必须在 {minimum} 到 {maximum} 之间。")
