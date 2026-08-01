from rest_framework import serializers

from scheduling.constants import ALLOWED_SLOT_INTERVAL_MINUTES, DEFAULT_SLOT_INTERVAL_MINUTES


class ScheduleRuleListQuerySerializer(serializers.Serializer):
    resource_id = serializers.IntegerField(required=False, allow_null=True)


class ScheduleRuleCreateRequestSerializer(serializers.Serializer):
    location_id = serializers.IntegerField()
    resource_id = serializers.IntegerField()
    days_of_week = serializers.ListField(
        child=serializers.IntegerField(min_value=0, max_value=6),
        allow_empty=False,
    )
    start_time = serializers.TimeField()
    end_time = serializers.TimeField()
    slot_interval_minutes = serializers.ChoiceField(
        choices=ALLOWED_SLOT_INTERVAL_MINUTES,
        default=DEFAULT_SLOT_INTERVAL_MINUTES,
    )
    capacity = serializers.IntegerField(min_value=1)


class ScheduleRuleUpdateRequestSerializer(serializers.Serializer):
    effective_date = serializers.DateField()
    location_id = serializers.IntegerField(required=False)
    resource_id = serializers.IntegerField(required=False)
    days_of_week = serializers.ListField(
        child=serializers.IntegerField(min_value=0, max_value=6),
        required=False,
    )
    start_time = serializers.TimeField(required=False)
    end_time = serializers.TimeField(required=False)
    slot_interval_minutes = serializers.ChoiceField(
        choices=ALLOWED_SLOT_INTERVAL_MINUTES,
        required=False,
    )
    capacity = serializers.IntegerField(min_value=1, required=False)
    is_active = serializers.BooleanField(required=False)


class ScheduleRuleResponseSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    location_id = serializers.IntegerField()
    resource_id = serializers.IntegerField()
    days_of_week = serializers.ListField(child=serializers.IntegerField())
    start_time = serializers.CharField()
    end_time = serializers.CharField()
    slot_interval_minutes = serializers.IntegerField()
    capacity = serializers.IntegerField()
    is_active = serializers.BooleanField()
    created_at = serializers.DateTimeField()
    updated_at = serializers.DateTimeField()


class ScheduleRuleListResponseSerializer(serializers.Serializer):
    rules = ScheduleRuleResponseSerializer(many=True)


class TimeSlotCreateRequestSerializer(serializers.Serializer):
    location_id = serializers.IntegerField()
    resource_id = serializers.IntegerField()
    start = serializers.DateTimeField()
    end = serializers.DateTimeField()
    capacity = serializers.IntegerField(min_value=1)


class TimeSlotCloseRequestSerializer(serializers.Serializer):
    pass


class TimeSlotBatchCloseRequestSerializer(serializers.Serializer):
    start = serializers.DateTimeField()
    end = serializers.DateTimeField()
    location_id = serializers.IntegerField(required=False, allow_null=True)
    resource_id = serializers.IntegerField(required=False, allow_null=True)


class TimeSlotResponseSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    location_id = serializers.IntegerField()
    resource_id = serializers.IntegerField()
    schedule_rule_id = serializers.IntegerField(allow_null=True)
    start = serializers.DateTimeField()
    end = serializers.DateTimeField()
    capacity = serializers.IntegerField()
    status = serializers.CharField()
    created_at = serializers.DateTimeField()
    updated_at = serializers.DateTimeField()


class TimeSlotBatchCloseResponseSerializer(serializers.Serializer):
    closed_count = serializers.IntegerField()


class TimeSlotBatchCloseConflictResponseSerializer(serializers.Serializer):
    conflicts = serializers.ListField(child=serializers.IntegerField())


class AvailabilityQueryRequestSerializer(serializers.Serializer):
    start = serializers.DateTimeField()
    end = serializers.DateTimeField()
    resource_id = serializers.IntegerField(required=False, allow_null=True)
    service_id = serializers.IntegerField(required=False, allow_null=True)
    location_id = serializers.IntegerField(required=False, allow_null=True)


class AvailabilityResourceSlotResponseSerializer(serializers.Serializer):
    time_slot_id = serializers.IntegerField()
    resource_id = serializers.IntegerField()
    location_id = serializers.IntegerField()
    start = serializers.CharField()
    end = serializers.CharField()
    capacity = serializers.IntegerField()
    remaining_capacity = serializers.IntegerField()


class AvailabilityAggregateItemResponseSerializer(serializers.Serializer):
    service_id = serializers.IntegerField()
    location_id = serializers.IntegerField()
    start = serializers.CharField()
    end = serializers.CharField()
    remaining_capacity = serializers.IntegerField()


class AvailabilityResourceQueryResponseSerializer(serializers.Serializer):
    mode = serializers.CharField()
    slots = AvailabilityResourceSlotResponseSerializer(many=True)


class AvailabilityAggregateQueryResponseSerializer(serializers.Serializer):
    mode = serializers.CharField()
    availability = AvailabilityAggregateItemResponseSerializer(many=True)


class BookingCreateRequestSerializer(serializers.Serializer):
    time_slot_id = serializers.IntegerField(required=False)
    service_id = serializers.IntegerField()
    location_id = serializers.IntegerField(required=False)
    start = serializers.DateTimeField(required=False)
    end = serializers.DateTimeField(required=False)
    resource_id = serializers.IntegerField(required=False)


class BookingResponseSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    status = serializers.CharField()
    contact_name = serializers.CharField()
    contact_phone = serializers.CharField()
    service_id = serializers.IntegerField()
    service_name = serializers.CharField()
    resource_id = serializers.IntegerField()
    resource_name = serializers.CharField()
    resource_is_active = serializers.BooleanField()
    location_id = serializers.IntegerField()
    location_name = serializers.CharField()
    location_address = serializers.CharField()
    location_is_active = serializers.BooleanField()
    time_slot_id = serializers.IntegerField()
    start = serializers.CharField()
    end = serializers.CharField()
    rescheduled_from_id = serializers.IntegerField(allow_null=True, required=False)
    rescheduled_to_id = serializers.IntegerField(allow_null=True, required=False)
    created_at = serializers.DateTimeField()


class BookingCancelRequestSerializer(serializers.Serializer):
    reason = serializers.CharField(required=False, allow_blank=True, default="")


class BookingRescheduleRequestSerializer(serializers.Serializer):
    time_slot_id = serializers.IntegerField()
    idempotency_key = serializers.CharField(max_length=128)


class BookingContactUpdateRequestSerializer(serializers.Serializer):
    contact_name = serializers.CharField(required=False, allow_blank=True, default="")
    contact_phone = serializers.CharField(required=False, allow_blank=True, default="")
    otp_code = serializers.CharField(required=False, allow_blank=True)


class BookingListResponseSerializer(serializers.Serializer):
    bookings = BookingResponseSerializer(many=True)


class StaffBookingCreateRequestSerializer(serializers.Serializer):
    time_slot_id = serializers.IntegerField()
    service_id = serializers.IntegerField()
    customer_id = serializers.IntegerField(required=False, allow_null=True)
    contact_name = serializers.CharField(required=False, allow_blank=True, default="")
    contact_phone = serializers.CharField(required=False, allow_blank=True, default="")


class StaffBookingResponseSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    status = serializers.CharField()
    contact_name = serializers.CharField()
    contact_phone = serializers.CharField()
    customer_phone = serializers.CharField(required=False)
    customer_id = serializers.IntegerField()
    service_id = serializers.IntegerField()
    resource_id = serializers.IntegerField()
    location_id = serializers.IntegerField()
    time_slot_id = serializers.IntegerField()
    start = serializers.CharField()
    end = serializers.CharField()
    rescheduled_from_id = serializers.IntegerField(allow_null=True, required=False)
    rescheduled_to_id = serializers.IntegerField(allow_null=True, required=False)
    created_at = serializers.DateTimeField()


class StaffBookingListResponseSerializer(serializers.Serializer):
    bookings = StaffBookingResponseSerializer(many=True)


class TimeSlotCapacityAdjustRequestSerializer(serializers.Serializer):
    capacity = serializers.IntegerField(min_value=1)
    reason = serializers.CharField(min_length=1)


class TenantBookingSettingsUpdateRequestSerializer(serializers.Serializer):
    min_advance_minutes = serializers.IntegerField(required=False, min_value=0)
    max_booking_window_days = serializers.IntegerField(required=False, min_value=1)
    pending_retention_minutes = serializers.IntegerField(required=False, min_value=1)
    cancel_deadline_minutes = serializers.IntegerField(required=False, min_value=0)
    future_booking_limit = serializers.IntegerField(required=False, min_value=1)
    confirmation_mode = serializers.ChoiceField(
        choices=["auto", "manual"],
        required=False,
    )


class TenantBookingSettingsResponseSerializer(serializers.Serializer):
    min_advance_minutes = serializers.IntegerField()
    max_booking_window_days = serializers.IntegerField()
    pending_retention_minutes = serializers.IntegerField()
    cancel_deadline_minutes = serializers.IntegerField()
    future_booking_limit = serializers.IntegerField()
    confirmation_mode = serializers.CharField()
    updated_at = serializers.DateTimeField()
