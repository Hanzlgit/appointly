from django.contrib.auth.models import User
from rest_framework import serializers


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
