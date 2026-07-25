from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from accounts import views

urlpatterns = [
    path("login/", views.StaffLoginView.as_view(), name="staff-login"),
    path("token/refresh/", TokenRefreshView.as_view(), name="token-refresh"),
]
