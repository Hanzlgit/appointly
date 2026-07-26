from rest_framework import serializers


class NotificationListItemResponseSerializer(serializers.Serializer):
    """单条站内通知响应。"""

    id = serializers.IntegerField()
    notification_type = serializers.CharField()
    title = serializers.CharField()
    body = serializers.CharField()
    booking_id = serializers.IntegerField(allow_null=True)
    read_at = serializers.DateTimeField(allow_null=True)
    created_at = serializers.DateTimeField()
