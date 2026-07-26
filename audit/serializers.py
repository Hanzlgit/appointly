from rest_framework import serializers


class AuditLogResponseSerializer(serializers.Serializer):
    """单条审计日志响应。"""

    id = serializers.IntegerField()
    action = serializers.CharField()
    target_type = serializers.CharField()
    target_id = serializers.IntegerField()
    operator_id = serializers.IntegerField(allow_null=True)
    operator_username = serializers.CharField(allow_null=True)
    request_id = serializers.CharField()
    ip_address = serializers.CharField(allow_null=True)
    before_value = serializers.DictField()
    after_value = serializers.DictField()
    details = serializers.DictField()
    created_at = serializers.DateTimeField()


class AuditLogListResponseSerializer(serializers.Serializer):
    """审计日志列表响应。"""

    logs = AuditLogResponseSerializer(many=True)
