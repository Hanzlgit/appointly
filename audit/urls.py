from django.urls import path

from audit import views

urlpatterns = [
    path("logs/", views.AuditLogListView.as_view(), name="audit-logs"),
]
