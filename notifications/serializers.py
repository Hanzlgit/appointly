from rest_framework import serializers

from notifications.constants import (
    DEFAULT_NOTIFICATION_PAGE_SIZE,
    MAX_NOTIFICATION_PAGE_SIZE,
    NOTIFICATION_TYPES,
)


class NotificationListQuerySerializer(serializers.Serializer):
    """通知列表查询参数。"""

    page = serializers.IntegerField(min_value=1, default=1, required=False)
    page_size = serializers.IntegerField(
        min_value=1,
        max_value=MAX_NOTIFICATION_PAGE_SIZE,
        default=DEFAULT_NOTIFICATION_PAGE_SIZE,
        required=False,
    )
    q = serializers.CharField(required=False, allow_blank=True, default="")
    unread_only = serializers.BooleanField(required=False, default=False)
    type = serializers.ChoiceField(
        choices=[(value, value) for value in NOTIFICATION_TYPES],
        required=False,
        allow_blank=True,
        default="",
    )


class NotificationListItemResponseSerializer(serializers.Serializer):
    """单条站内通知响应。"""

    id = serializers.IntegerField()
    notification_type = serializers.CharField()
    title = serializers.CharField()
    body = serializers.CharField()
    queue_ticket_id = serializers.IntegerField(allow_null=True)
    read_at = serializers.DateTimeField(allow_null=True)
    created_at = serializers.DateTimeField()


class NotificationListResponseSerializer(serializers.Serializer):
    """分页通知列表响应。"""

    items = NotificationListItemResponseSerializer(many=True)
    total = serializers.IntegerField()
    page = serializers.IntegerField()
    page_size = serializers.IntegerField()
    unread_count = serializers.IntegerField()


class NotificationReadAllResponseSerializer(serializers.Serializer):
    """全部标记已读响应。"""

    marked_count = serializers.IntegerField()
