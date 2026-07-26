from __future__ import annotations

from typing import Any

from rest_framework.response import Response


def build_envelope(
    *,
    data: Any,
    code: int = 0,
    message: str = "ok",
    request_id: str = "",
) -> dict[str, Any]:
    """构建标准 API 响应体。

    Args:
        data (Any): 业务载荷。
        code (int): 业务码，``0`` 表示成功。
        message (str): 人类可读说明。
        request_id (str): 请求追踪 ID。

    Returns:
        dict[str, Any]: 含 ``code``、``message``、``data``、``request_id`` 的字典。
    """
    return {
        "code": code,
        "message": message,
        "data": data,
        "request_id": request_id,
    }


def api_response(
    request,
    *,
    data: Any = None,
    message: str = "ok",
    code: int = 0,
    status: int = 200,
) -> Response:
    """返回包装为标准 envelope 的 DRF Response。

    Args:
        request: Django / DRF 请求对象，用于读取 ``request_id``。
        data (Any): 业务载荷，默认 ``None``。
        message (str): 人类可读说明。
        code (int): 业务码，``0`` 表示成功。
        status (int): HTTP 状态码。

    Returns:
        Response: 标准 envelope 格式的 DRF 响应。
    """
    request_id = getattr(request, "request_id", "")
    body = build_envelope(code=code, message=message, data=data, request_id=request_id)
    return Response(body, status=status)


def request_id_from(request) -> str:
    """从请求对象读取 request_id。

    Args:
        request: Django / DRF 请求对象。

    Returns:
        str: 请求追踪 ID；未注入时返回空字符串。
    """
    return getattr(request, "request_id", "")
