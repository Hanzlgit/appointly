"""从 HTTP 请求提取审计上下文。"""

from __future__ import annotations

from django.contrib.auth.models import User
from rest_framework.request import Request


def audit_http_context(*, request: Request) -> dict:
    """从 DRF 请求提取审计写入所需上下文。

    Args:
        request (Request): DRF 请求对象。

    Returns:
        dict: 含 ``request_id``、``ip_address``、``operator`` 的字典。
    """
    operator: User | None = request.user if request.user.is_authenticated else None
    return {
        "request_id": getattr(request, "request_id", ""),
        "ip_address": request.META.get("REMOTE_ADDR"),
        "operator": operator,
    }
