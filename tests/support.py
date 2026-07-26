"""Test helpers for API envelope responses."""


def response_body(response) -> dict:
    """解析 HTTP 响应 JSON  body。

    Args:
        response: DRF / Django 测试客户端响应对象。

    Returns:
        dict: 解析后的 JSON 字典。
    """
    return response.json()


def api_data(response) -> dict | list | None:
    """从 envelope 响应中提取 ``data`` 字段。

    Args:
        response: DRF / Django 测试客户端响应对象。

    Returns:
        dict | list | None: 响应体中的 ``data`` 载荷。
    """
    body = response_body(response)
    assert "data" in body, body
    return body["data"]


def api_message(response) -> str:
    """从 envelope 响应中提取 ``message`` 字段。

    Args:
        response: DRF / Django 测试客户端响应对象。

    Returns:
        str: 响应体中的 ``message`` 文本。
    """
    return response_body(response)["message"]


def api_code(response) -> int:
    """从 envelope 响应中提取 ``code`` 字段。

    Args:
        response: DRF / Django 测试客户端响应对象。

    Returns:
        int: 响应体中的业务码。
    """
    return response_body(response)["code"]
