from django.urls import path

from scheduling import views

urlpatterns = [
    path(
        "availability/",
        views.AvailabilityQueryView.as_view(),
        name="scheduling-availability",
    ),
    path(
        "bookings/",
        views.BookingListCreateView.as_view(),
        name="scheduling-bookings",
    ),
    path(
        "bookings/<int:booking_id>/confirm/",
        views.BookingConfirmView.as_view(),
        name="scheduling-booking-confirm",
    ),
    path(
        "bookings/<int:booking_id>/reject/",
        views.BookingRejectView.as_view(),
        name="scheduling-booking-reject",
    ),
    path(
        "booking-settings/",
        views.TenantBookingSettingsView.as_view(),
        name="scheduling-booking-settings",
    ),
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
