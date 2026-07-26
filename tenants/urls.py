from django.urls import path

from tenants import views

urlpatterns = [
    path("context/", views.TenantContextView.as_view(), name="tenant-context"),
    path("membership/", views.TenantMembershipView.as_view(), name="tenant-membership"),
    path("records/", views.TenantScopedRecordView.as_view(), name="tenant-records"),
    path("customer/me/", views.TenantCustomerMeView.as_view(), name="tenant-customer-me"),
]
