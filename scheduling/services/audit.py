"""预约相关审计记录桩（完整审计见 issue 12）。"""

from __future__ import annotations

from typing import Any

_AUDIT_ENTRIES: list[dict[str, Any]] = []


def scheduling_audit_record(
    *,
    tenant_id: int,
    operator_id: int,
    action: str,
    target_type: str,
    target_id: int,
    details: dict[str, Any] | None = None,
) -> None:
    """记录一条不可变审计条目。

    Args:
        tenant_id (int): 租户 ID。
        operator_id (int): 操作人用户 ID。
        action (str): 操作类型标识。
        target_type (str): 目标对象类型。
        target_id (int): 目标对象 ID。
        details (dict[str, Any] | None): 附加详情。
    """
    _AUDIT_ENTRIES.append(
        {
            "tenant_id": tenant_id,
            "operator_id": operator_id,
            "action": action,
            "target_type": target_type,
            "target_id": target_id,
            "details": details or {},
        }
    )


def scheduling_audit_list(*, tenant_id: int | None = None) -> list[dict[str, Any]]:
    """列出审计条目，测试与调试使用。

    Args:
        tenant_id (int | None): 可选租户过滤。

    Returns:
        list[dict[str, Any]]: 审计条目副本列表。
    """
    if tenant_id is None:
        return list(_AUDIT_ENTRIES)
    return [entry for entry in _AUDIT_ENTRIES if entry["tenant_id"] == tenant_id]


def scheduling_audit_clear_for_tests() -> None:
    """清空内存审计条目，仅测试使用。"""
    _AUDIT_ENTRIES.clear()
