from django.urls import include, path

from appointly import views
from queuing.urls import console_urlpatterns

urlpatterns = [
    path("ping/", views.PingView.as_view(), name="ping"),
    path("auth/", include("accounts.urls")),
    path("", include("catalog.urls")),
    path("queue/", include("queuing.urls")),
    path("notifications/", include("notifications.urls")),
    path("console/", include("catalog.urls")),
    path("console/", include(console_urlpatterns)),
]
