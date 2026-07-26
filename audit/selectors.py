"""审计日志读取选择器。"""

from __future__ import annotations

from typing import Any

from django.contrib.auth.models import User
from scheduling.selectors import scheduling_phone_mask
from tenants.models import Tenant, TenantRole

from audit.models import AuditLog


def audit_log_list_for_tenant(
    *,
    tenant: Tenant,
    action: str | None = None,
    target_type: str | None = None,
    limit: int = 100,
) -> list[AuditLog]:
    """列出租户审计日志。

    Args:
        tenant (Tenant): 目标租户。
        action (str | None): 可选操作类型过滤。
        target_type (str | None): 可选目标类型过滤。
        limit (int): 最大返回条数。

    Returns:
        list[AuditLog]: 审计记录列表，按创建时间倒序。
    """
    queryset = AuditLog.objects.filter(tenant=tenant).select_related("operator")
    if action is not None:
        queryset = queryset.filter(action=action)
    if target_type is not None:
        queryset = queryset.filter(target_type=target_type)
    return list(queryset.order_by("-created_at")[:limit])


def _audit_log_mask_sensitive_fields(*, payload: dict[str, Any]) -> dict[str, Any]:
    """对字典中的手机号字段脱敏。

    Args:
        payload (dict[str, Any]): 原始 JSON 字段。

    Returns:
        dict[str, Any]: 脱敏后的副本。
    """
    masked = dict(payload)
    for key in ("contact_phone", "phone", "customer_phone"):
        if key in masked and isinstance(masked[key], str) and masked[key]:
            masked[key] = scheduling_phone_mask(phone=masked[key])
    return masked


def audit_log_to_dict(*, log: AuditLog, viewer_role: str) -> dict:
    """将审计记录映射为 API 响应字典。

    Args:
        log (AuditLog): 审计记录实例。
        viewer_role (str): 查看者角色。

    Returns:
        dict: 含审计字段的响应字典。
    """
    can_view_sensitive = viewer_role in {TenantRole.TENANT_ADMIN, "platform_admin"}
    before_value = log.before_value
    after_value = log.after_value
    details = log.details
    if not can_view_sensitive:
        before_value = _audit_log_mask_sensitive_fields(payload=before_value)
        after_value = _audit_log_mask_sensitive_fields(payload=after_value)
        details = _audit_log_mask_sensitive_fields(payload=details)

    return {
        "id": log.id,
        "action": log.action,
        "target_type": log.target_type,
        "target_id": log.target_id,
        "operator_id": log.operator_id,
        "operator_username": log.operator.username if log.operator_id else None,
        "request_id": log.request_id,
        "ip_address": log.ip_address,
        "before_value": before_value,
        "after_value": after_value,
        "details": details,
        "created_at": log.created_at,
    }


def audit_log_operator_display(*, operator: User | None) -> str | None:
    """返回操作人展示名。

    Args:
        operator (User | None): 操作人用户。

    Returns:
        str | None: 用户名或 ``None``。
    """
    if operator is None:
        return None
    return operator.username
