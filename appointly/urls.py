from django.urls import include, path

from appointly import views

urlpatterns = [
    path("ping/", views.PingView.as_view(), name="ping"),
    path("auth/", include("accounts.urls")),
]
