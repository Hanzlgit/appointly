"""时段容量调整服务。"""

from __future__ import annotations

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import transaction
from tenants.models import Tenant

from scheduling.models import TimeSlot
from scheduling.services.audit import scheduling_audit_record


def scheduling_timeslot_capacity_adjust(
    *,
    tenant: Tenant,
    time_slot: TimeSlot,
    capacity: int,
    reason: str,
    operator: User,
    request_id: str = "",
    ip_address: str | None = None,
) -> TimeSlot:
    """管理员显式调整固定时段容量并记录原因。

    Args:
        tenant (Tenant): 目标租户。
        time_slot (TimeSlot): 待调整时段。
        capacity (int): 新容量（不小于 1）。
        reason (str): 调整原因。
        operator (User): 操作人。

    Returns:
        TimeSlot: 更新后的固定时段。

    Raises:
        ValidationError: 容量无效或原因为空。
    """
    normalized_reason = reason.strip()
    if not normalized_reason:
        raise ValidationError("调整容量必须填写原因。")
    if capacity < 1:
        raise ValidationError("容量必须不小于 1。")
    if time_slot.tenant_id != tenant.id:
        raise ValidationError("时段不属于当前租户。")

    old_capacity = time_slot.capacity
    if old_capacity == capacity:
        return time_slot

    with transaction.atomic():
        locked = TimeSlot.objects.select_for_update().get(pk=time_slot.pk)
        locked.capacity = capacity
        locked.save(update_fields=["capacity", "updated_at"])
        scheduling_audit_record(
            tenant_id=tenant.id,
            operator_id=operator.id,
            action="capacity_adjust",
            target_type="time_slot",
            target_id=locked.id,
            before_value={"capacity": old_capacity},
            after_value={"capacity": capacity},
            details={"reason": normalized_reason},
            request_id=request_id,
            ip_address=ip_address,
        )
        return locked
