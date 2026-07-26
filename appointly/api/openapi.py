from rest_framework import serializers


class ApiEnvelopeSerializer(serializers.Serializer):
    code = serializers.IntegerField(help_text="业务码，0 表示成功")
    message = serializers.CharField(help_text="人类可读说明")
    request_id = serializers.CharField(help_text="请求追踪 ID")


class ApiEnvelopeWithNullDataSerializer(ApiEnvelopeSerializer):
    data = serializers.JSONField(allow_null=True, help_text="业务载荷")


def enveloped_response_serializer(data_serializer: type[serializers.Serializer]):
    """为 OpenAPI 文档生成含 envelope 的响应 Serializer。

    Args:
        data_serializer (type[Serializer]): 描述 ``data`` 字段结构的 Serializer 类。

    Returns:
        type[Serializer]: 含 ``code``、``message``、``data``、``request_id`` 的动态 Serializer。
    """

    class EnvelopedResponseSerializer(ApiEnvelopeSerializer):
        data = data_serializer()

    return EnvelopedResponseSerializer
