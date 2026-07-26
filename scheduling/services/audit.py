"""预约相关审计记录（委托 audit 应用）。"""

from __future__ import annotations

from typing import Any

from audit.services.audit_log import audit_log_record
from django.contrib.auth.models import User
from tenants.models import Tenant


def scheduling_audit_record(
    *,
    tenant_id: int,
    operator_id: int,
    action: str,
    target_type: str,
    target_id: int,
    details: dict[str, Any] | None = None,
    before_value: dict[str, Any] | None = None,
    after_value: dict[str, Any] | None = None,
    request_id: str = "",
    ip_address: str | None = None,
) -> None:
    """记录一条不可变审计条目。

    Args:
        tenant_id (int): 租户 ID。
        operator_id (int): 操作人用户 ID。
        action (str): 操作类型标识。
        target_type (str): 目标对象类型。
        target_id (int): 目标对象 ID。
        details (dict[str, Any] | None): 附加详情。
        before_value (dict[str, Any] | None): 变更前值。
        after_value (dict[str, Any] | None): 变更后值。
        request_id (str): 关联请求 ID。
        ip_address (str | None): 客户端 IP。
    """
    tenant = Tenant.objects.get(pk=tenant_id)
    operator = User.objects.get(pk=operator_id)
    audit_log_record(
        tenant=tenant,
        operator=operator,
        request_id=request_id,
        ip_address=ip_address,
        action=action,
        target_type=target_type,
        target_id=target_id,
        before_value=before_value,
        after_value=after_value,
        details=details,
    )


def scheduling_audit_list(*, tenant_id: int | None = None) -> list[dict[str, Any]]:
    """列出审计条目，测试与调试使用。

    Args:
        tenant_id (int | None): 可选租户过滤。

    Returns:
        list[dict[str, Any]]: 审计条目副本列表。
    """
    from audit.models import AuditLog

    queryset = AuditLog.objects.all().order_by("id")
    if tenant_id is not None:
        queryset = queryset.filter(tenant_id=tenant_id)
    return [
        {
            "tenant_id": entry.tenant_id,
            "operator_id": entry.operator_id,
            "action": entry.action,
            "target_type": entry.target_type,
            "target_id": entry.target_id,
            "before_value": entry.before_value,
            "after_value": entry.after_value,
            "details": entry.details,
            "request_id": entry.request_id,
        }
        for entry in queryset
    ]


def scheduling_audit_clear_for_tests() -> None:
    """清空审计条目，仅测试使用。"""
    from audit.models import AuditLog

    AuditLog.objects.all().delete()
