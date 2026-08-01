from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView


def health_live(_request):
    """Kubernetes liveness 探针：进程存活即返回 ok。

    Args:
        _request: Django 请求对象（未使用）。

    Returns:
        JsonResponse: ``{"status": "ok"}``。
    """
    return JsonResponse({"status": "ok"})


def health_ready(_request):
    """Kubernetes readiness 探针：数据库可连接时返回 ready。

    Args:
        _request: Django 请求对象（未使用）。

    Returns:
        JsonResponse: 就绪时 ``{"status": "ready"}``；不可用时 HTTP 503。
    """
    from django.db import connection

    try:
        connection.ensure_connection()
    except Exception:
        return JsonResponse({"status": "unavailable"}, status=503)
    return JsonResponse({"status": "ready"})


urlpatterns = [
    path("admin/", admin.site.urls),
    path("health/live", health_live, name="health-live"),
    path("health/ready", health_ready, name="health-ready"),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
    path("api/v1/", include("appointly.urls")),
]
