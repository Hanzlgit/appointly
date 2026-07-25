from django.urls import include, path

from appointly import views

urlpatterns = [
    path("ping/", views.ping, name="ping"),
    path("auth/", include("accounts.urls")),
]
