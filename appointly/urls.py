from django.urls import path

from appointly import views

urlpatterns = [
    path("ping/", views.ping, name="ping"),
]
