from django.urls import path

from audit import dashboard_views

urlpatterns = [
    path("summary/", dashboard_views.DashboardSummaryView.as_view(), name="dashboard-summary"),
]
