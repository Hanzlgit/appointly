"""审计日志写入服务。"""

from __future__ import annotations

from typing import Any

from django.contrib.auth.models import User
from tenants.models import Tenant

from audit.models import AuditLog


def audit_log_record(
    *,
    tenant: Tenant,
    operator: User | None,
    request_id: str = "",
    ip_address: str | None = None,
    action: str,
    target_type: str,
    target_id: int,
    before_value: dict[str, Any] | None = None,
    after_value: dict[str, Any] | None = None,
    details: dict[str, Any] | None = None,
) -> AuditLog:
    """写入一条不可变审计记录。

    Args:
        tenant (Tenant): 所属租户。
        operator (User | None): 操作人；系统操作时可为 ``None``。
        request_id (str): 关联请求 ID。
        ip_address (str | None): 客户端 IP。
        action (str): 操作类型标识。
        target_type (str): 目标对象类型。
        target_id (int): 目标对象 ID。
        before_value (dict[str, Any] | None): 变更前值。
        after_value (dict[str, Any] | None): 变更后值。
        details (dict[str, Any] | None): 附加详情。

    Returns:
        AuditLog: 新建的审计记录。
    """
    return AuditLog.objects.create(
        tenant=tenant,
        operator=operator,
        request_id=request_id,
        ip_address=ip_address,
        action=action,
        target_type=target_type,
        target_id=target_id,
        before_value=before_value or {},
        after_value=after_value or {},
        details=details or {},
    )


def audit_log_booking_status_change(
    *,
    tenant: Tenant,
    booking_id: int,
    old_status: str,
    new_status: str,
    request,
) -> AuditLog:
    """记录预约状态变更审计。

    Args:
        tenant (Tenant): 所属租户。
        booking_id (int): 预约 ID。
        old_status (str): 变更前状态。
        new_status (str): 变更后状态。
        request: DRF 请求对象。

    Returns:
        AuditLog: 新建的审计记录。
    """
    from audit.constants import AuditAction
    from audit.services.http_context import audit_http_context

    http_context = audit_http_context(request=request)
    return audit_log_record(
        tenant=tenant,
        operator=http_context["operator"],
        request_id=http_context["request_id"],
        ip_address=http_context["ip_address"],
        action=AuditAction.BOOKING_STATUS_CHANGE,
        target_type="booking",
        target_id=booking_id,
        before_value={"status": old_status},
        after_value={"status": new_status},
    )
