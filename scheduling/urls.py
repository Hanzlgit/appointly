from django.urls import path

from scheduling import views

urlpatterns = [
    path(
        "rules/",
        views.ScheduleRuleListCreateView.as_view(),
        name="scheduling-rules",
    ),
    path(
        "rules/<int:rule_id>/",
        views.ScheduleRuleUpdateView.as_view(),
        name="scheduling-rule-detail",
    ),
    path(
        "time-slots/",
        views.TimeSlotCreateView.as_view(),
        name="scheduling-time-slots",
    ),
    path(
        "time-slots/batch-close/",
        views.TimeSlotBatchCloseView.as_view(),
        name="scheduling-time-slots-batch-close",
    ),
    path(
        "time-slots/<int:time_slot_id>/close/",
        views.TimeSlotCloseView.as_view(),
        name="scheduling-time-slot-close",
    ),
]
