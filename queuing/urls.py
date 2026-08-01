from django.urls import path

from queuing import views

urlpatterns = [
    path("tickets/", views.QueueTicketListCreateView.as_view(), name="queue-tickets"),
    path(
        "tickets/<int:ticket_id>/",
        views.QueueTicketRetrieveView.as_view(),
        name="queue-ticket-detail",
    ),
    path(
        "tickets/<int:ticket_id>/cancel/",
        views.QueueTicketCancelView.as_view(),
        name="queue-ticket-cancel",
    ),
]

console_urlpatterns = [
    path(
        "stylists/<int:stylist_id>/queue/",
        views.ConsoleStylistQueueListView.as_view(),
        name="console-stylist-queue",
    ),
    path(
        "queue/tickets/<int:ticket_id>/call/",
        views.ConsoleQueueTicketCallView.as_view(),
        name="console-queue-ticket-call",
    ),
    path(
        "queue/tickets/<int:ticket_id>/start/",
        views.ConsoleQueueTicketStartView.as_view(),
        name="console-queue-ticket-start",
    ),
    path(
        "queue/tickets/<int:ticket_id>/complete/",
        views.ConsoleQueueTicketCompleteView.as_view(),
        name="console-queue-ticket-complete",
    ),
    path(
        "queue/tickets/<int:ticket_id>/cancel/",
        views.ConsoleQueueTicketCancelView.as_view(),
        name="console-queue-ticket-cancel",
    ),
    path(
        "queue/tickets/<int:ticket_id>/move-to-tail/",
        views.ConsoleQueueTicketMoveToTailView.as_view(),
        name="console-queue-ticket-move-to-tail",
    ),
    path(
        "stylists/<int:stylist_id>/queue-status/",
        views.ConsoleStylistQueueStatusUpdateView.as_view(),
        name="console-stylist-queue-status",
    ),
]
