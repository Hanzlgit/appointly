from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from accounts import views

urlpatterns = [
    path("login/", views.StaffLoginView.as_view(), name="staff-login"),
    path("token/refresh/", TokenRefreshView.as_view(), name="token-refresh"),
    path("customer/otp/send/", views.CustomerOtpSendView.as_view(), name="customer-otp-send"),
    path(
        "customer/otp/verify/",
        views.CustomerOtpVerifyView.as_view(),
        name="customer-otp-verify",
    ),
]
