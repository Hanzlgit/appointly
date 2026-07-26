from django.urls import path

from tenants import views

urlpatterns = [
    path("context/", views.TenantContextRetrieveView.as_view(), name="tenant-context"),
    path("membership/", views.TenantMembershipRetrieveView.as_view(), name="tenant-membership"),
    path(
        "records/",
        views.TenantScopedRecordListCreateView.as_view(),
        name="tenant-records",
    ),
    path(
        "customers/me/",
        views.TenantCustomerMeRetrieveView.as_view(),
        name="tenant-customer-me",
    ),
]
