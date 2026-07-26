from __future__ import annotations

from typing import Any

from rest_framework.exceptions import APIException
from rest_framework.views import exception_handler

from appointly.api.envelope import build_envelope, request_id_from


def _message_from_response_data(response_data: Any) -> str:
    """从 DRF 错误响应体提取人类可读消息。

    Args:
        response_data (Any): DRF 异常响应的 ``data`` 字段。

    Returns:
        str: 合并后的错误说明文本。
    """
    if isinstance(response_data, dict):
        if "detail" in response_data:
            detail = response_data["detail"]
            if isinstance(detail, list):
                return "; ".join(str(item) for item in detail)
            return str(detail)
        if len(response_data) == 1:
            key = next(iter(response_data))
            value = response_data[key]
            if isinstance(value, list):
                return f"{key}: {value[0]}"
            return f"{key}: {value}"
    if isinstance(response_data, list):
        return "; ".join(str(item) for item in response_data)
    return str(response_data)


def _business_code_for_status(http_status: int) -> int:
    """将 HTTP 状态码映射为 envelope 业务码。

    Args:
        http_status (int): HTTP 响应状态码。

    Returns:
        int: envelope 中的 ``code`` 字段值。
    """
    return http_status if http_status != 200 else 0


def api_exception_handler(exc, context):
    """将 DRF 异常响应包装为标准 envelope。

    Args:
        exc: 捕获的异常实例。
        context (dict): DRF 异常处理上下文，含 ``request`` 等键。

    Returns:
        Response | None: 包装后的响应；未处理时重新抛出原异常。
    """
    response = exception_handler(exc, context)
    request = context.get("request")

    if response is not None:
        message = _message_from_response_data(response.data)
        if isinstance(exc, APIException) and exc.detail and message == str(exc.detail):
            pass
        response.data = build_envelope(
            code=_business_code_for_status(response.status_code),
            message=message,
            data=response.data,
            request_id=request_id_from(request),
        )
        return response

    raise exc
