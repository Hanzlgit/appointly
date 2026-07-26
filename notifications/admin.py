from django.contrib import admin

from notifications.models import Notification, OutboxEvent, ProcessedEvent


@admin.register(OutboxEvent)
class OutboxEventAdmin(admin.ModelAdmin):
    list_display = ("event_id", "event_type", "tenant", "published_at", "created_at")
    list_filter = ("event_type", "published_at")
    search_fields = ("event_id", "aggregate_id")


@admin.register(ProcessedEvent)
class ProcessedEventAdmin(admin.ModelAdmin):
    list_display = ("event_id", "processed_at")


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("notification_type", "recipient", "tenant", "read_at", "created_at")
    list_filter = ("notification_type", "read_at")
