from drf_spectacular.utils import OpenApiExample, extend_schema
from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from accounts.serializers import StaffLoginSerializer


class StaffLoginResponseSerializer(serializers.Serializer):
    access = serializers.CharField(help_text="JWT Access Token，默认 15 分钟有效")
    refresh = serializers.CharField(help_text="JWT Refresh Token，默认 7 天有效")


class StaffLoginView(APIView):
    authentication_classes = []
    permission_classes = []

    @extend_schema(
        summary="后台用户登录",
        description="使用用户名或手机号加密码登录，返回 access 与 refresh token。",
        request=StaffLoginSerializer,
        responses={200: StaffLoginResponseSerializer},
        examples=[
            OpenApiExample(
                "用户名登录",
                value={"login": "acme-admin", "password": "StrongPass123!"},
                request_only=True,
            ),
            OpenApiExample(
                "手机号登录",
                value={"login": "13800138000", "password": "StrongPass123!"},
                request_only=True,
            ),
        ],
    )
    def post(self, request, *args, **kwargs):
        serializer = StaffLoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        refresh = RefreshToken.for_user(serializer.validated_data["user"])
        return Response(
            {"access": str(refresh.access_token), "refresh": str(refresh)},
            status=status.HTTP_200_OK,
        )
