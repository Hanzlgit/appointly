import re

from django.contrib.auth.models import User
from rest_framework import serializers

_PHONE_PATTERN = re.compile(r"^1\d{10}$")


class StaffLoginSerializer(serializers.Serializer):
    login = serializers.CharField(help_text="用户名或手机号")
    password = serializers.CharField(write_only=True, help_text="密码")

    def validate(self, attrs):
        login = attrs["login"]
        password = attrs["password"]

        user = User.objects.filter(username=login).first()
        if user is None:
            user = (
                User.objects.filter(staff_profile__phone=login)
                .select_related("staff_profile")
                .first()
            )

        if user is None or not user.check_password(password):
            raise serializers.ValidationError("用户名或密码错误。")

        attrs["user"] = user
        return attrs


class PhoneField(serializers.CharField):
    def __init__(self, **kwargs):
        kwargs.setdefault("help_text", "中国大陆手机号")
        kwargs.setdefault("max_length", 32)
        super().__init__(**kwargs)

    def to_internal_value(self, data):
        phone = super().to_internal_value(data).strip()
        if not _PHONE_PATTERN.fullmatch(phone):
            raise serializers.ValidationError("手机号格式不正确。")
        return phone


class CustomerOtpSendRequestSerializer(serializers.Serializer):
    phone = PhoneField()


class CustomerOtpSendResponseSerializer(serializers.Serializer):
    detail = serializers.CharField()


class CustomerOtpVerifyRequestSerializer(serializers.Serializer):
    phone = PhoneField()
    code = serializers.CharField(help_text="短信验证码", max_length=16)
    tenant_slug = serializers.SlugField(help_text="租户 slug，用于建立租户客户档案")


class CustomerOtpVerifyResponseSerializer(serializers.Serializer):
    access = serializers.CharField(help_text="JWT Access Token，默认 15 分钟有效")
    refresh = serializers.CharField(help_text="JWT Refresh Token，默认 7 天有效")
