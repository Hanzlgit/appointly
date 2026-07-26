from django.urls import path

from accounts import views

urlpatterns = [
    path("staff/sessions/", views.StaffSessionCreateView.as_view(), name="staff-session-create"),
    path("tokens/refresh/", views.TokenRefreshView.as_view(), name="token-refresh"),
    path(
        "customer/verification-codes/",
        views.CustomerVerificationCodeCreateView.as_view(),
        name="customer-verification-code-create",
    ),
    path(
        "customer/sessions/",
        views.CustomerSessionCreateView.as_view(),
        name="customer-session-create",
    ),
]
