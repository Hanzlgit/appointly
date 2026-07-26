import uuid


class RequestIdMiddleware:
    """为每个请求注入唯一 request_id 并在响应头中回传。"""

    def __init__(self, get_response):
        """初始化 middleware。

        Args:
            get_response: Django 下游 callable。
        """
        self.get_response = get_response

    def __call__(self, request):
        """处理请求并注入 request_id。

        Args:
            request: Django 请求对象。

        Returns:
            HttpResponse: 附带 ``X-Request-ID`` 响应头的下游响应。
        """
        request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex
        request.request_id = request_id
        response = self.get_response(request)
        response["X-Request-ID"] = request_id
        return response
