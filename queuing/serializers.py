from rest_framework import serializers


class QueueListQuerySerializer(serializers.Serializer):
    """管理台队列查询参数。"""

    page = serializers.IntegerField(min_value=1, default=1, required=False)
    page_size = serializers.IntegerField(min_value=1, max_value=100, default=20, required=False)
    status = serializers.CharField(required=False, allow_blank=True, default="")
    q = serializers.CharField(required=False, allow_blank=True, default="")


class QueueTicketCreateRequestSerializer(serializers.Serializer):
    """取号请求体。"""

    stylist_id = serializers.IntegerField(min_value=1)
    service_id = serializers.IntegerField(min_value=1)
    idempotency_key = serializers.CharField(max_length=128)


class QueueTicketResponseSerializer(serializers.Serializer):
    """排队号响应体。"""

    id = serializers.IntegerField()
    ticket_display = serializers.CharField()
    ticket_number = serializers.IntegerField()
    status = serializers.CharField()
    position = serializers.IntegerField()
    ahead_count = serializers.IntegerField()
    estimated_wait_minutes = serializers.IntegerField()
    location_id = serializers.IntegerField()
    location_name = serializers.CharField()
    stylist_id = serializers.IntegerField()
    stylist_name = serializers.CharField()
    service_id = serializers.IntegerField()
    service_name = serializers.CharField()
    service_duration_minutes = serializers.IntegerField()
    service_price_cents = serializers.IntegerField()
    queue_date = serializers.DateField()
    created_at = serializers.DateTimeField()


class QueueTicketListResponseSerializer(serializers.Serializer):
    """管理台队列列表响应。"""

    items = QueueTicketResponseSerializer(many=True)
    total = serializers.IntegerField()
    page = serializers.IntegerField()
    page_size = serializers.IntegerField()


class QueueTicketCancelRequestSerializer(serializers.Serializer):
    """取消排队请求体。"""

    reason = serializers.CharField(required=False, allow_blank=True, default="")


class ConsoleQueueTicketActionRequestSerializer(serializers.Serializer):
    """管理台排队操作请求体。"""

    reason = serializers.CharField(required=False, allow_blank=True, default="")


class StylistQueueStatusUpdateRequestSerializer(serializers.Serializer):
    """理发师接单状态更新请求体。"""

    queue_status = serializers.ChoiceField(choices=["open", "paused", "closed"])
