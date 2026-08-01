import re

from rest_framework import serializers

_PHONE_PATTERN = re.compile(r"^1\d{10}$")


class StaffSessionCreateRequestSerializer(serializers.Serializer):
    login = serializers.CharField(help_text="用户名或手机号")
    password = serializers.CharField(write_only=True, help_text="密码")


class StaffSessionCreateResponseSerializer(serializers.Serializer):
    access = serializers.CharField(help_text="JWT Access Token，默认 15 分钟有效")
    refresh = serializers.CharField(help_text="JWT Refresh Token，默认 7 天有效")


class TokenRefreshRequestSerializer(serializers.Serializer):
    refresh = serializers.CharField(help_text="Refresh Token")


class TokenRefreshResponseSerializer(serializers.Serializer):
    access = serializers.CharField(help_text="新的 Access Token")
    refresh = serializers.CharField(help_text="新的 Refresh Token")


class PhoneField(serializers.CharField):
    def __init__(self, **kwargs):
        """初始化中国大陆手机号字段默认值。

        Args:
            **kwargs: 传给 ``CharField`` 的额外参数。
        """
        kwargs.setdefault("help_text", "中国大陆手机号")
        kwargs.setdefault("max_length", 32)
        super().__init__(**kwargs)

    def to_internal_value(self, data):
        """校验并规范化手机号为 11 位大陆号码。

        Args:
            data: 原始输入值。

        Returns:
            str: 规范化后的手机号。

        Raises:
            ValidationError: 格式不符合 ``1`` 开头的 11 位数字。
        """
        phone = super().to_internal_value(data).strip()
        if not _PHONE_PATTERN.fullmatch(phone):
            raise serializers.ValidationError("手机号格式不正确。")
        return phone


class CustomerVerificationCodeCreateRequestSerializer(serializers.Serializer):
    phone = PhoneField()


class CustomerSessionCreateRequestSerializer(serializers.Serializer):
    phone = PhoneField()
    code = serializers.CharField(help_text="短信验证码", max_length=16)


class CustomerSessionCreateResponseSerializer(serializers.Serializer):
    access = serializers.CharField(help_text="JWT Access Token，默认 15 分钟有效")
    refresh = serializers.CharField(help_text="JWT Refresh Token，默认 7 天有效")
