from django.core.exceptions import ValidationError as DjangoValidationError
from drf_spectacular.utils import OpenApiExample, extend_schema
from rest_framework import serializers, status
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from tenants.models import Tenant

from accounts.serializers import (
    CustomerOtpSendRequestSerializer,
    CustomerOtpSendResponseSerializer,
    CustomerOtpVerifyRequestSerializer,
    CustomerOtpVerifyResponseSerializer,
    StaffLoginSerializer,
)
from accounts.services.customer_auth import customer_authenticate, customer_tokens_issue
from accounts.services.otp import customer_otp_send


def _raise_validation_error(exc: DjangoValidationError) -> None:
    if hasattr(exc, "message_dict"):
        raise ValidationError(exc.message_dict) from exc
    if hasattr(exc, "messages"):
        raise ValidationError(exc.messages) from exc
    raise ValidationError(str(exc)) from exc


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


class CustomerOtpSendView(APIView):
    authentication_classes = []
    permission_classes = []

    @extend_schema(
        summary="发送客户登录验证码",
        description="向手机号发送登录验证码（开发环境使用 Mock 短信适配器）。",
        request=CustomerOtpSendRequestSerializer,
        responses={200: CustomerOtpSendResponseSerializer},
        examples=[
            OpenApiExample(
                "发送验证码",
                value={"phone": "13900139000"},
                request_only=True,
            ),
        ],
    )
    def post(self, request, *args, **kwargs):
        request_serializer = CustomerOtpSendRequestSerializer(data=request.data)
        request_serializer.is_valid(raise_exception=True)

        try:
            customer_otp_send(phone=request_serializer.validated_data["phone"])
        except DjangoValidationError as exc:
            _raise_validation_error(exc)

        response_serializer = CustomerOtpSendResponseSerializer({"detail": "验证码已发送。"})
        return Response(response_serializer.data, status=status.HTTP_200_OK)


class CustomerOtpVerifyView(APIView):
    authentication_classes = []
    permission_classes = []

    @extend_schema(
        summary="校验客户登录验证码",
        description="校验验证码并签发 JWT；首次验证自动创建平台账号，并确保租户客户档案存在。",
        request=CustomerOtpVerifyRequestSerializer,
        responses={200: CustomerOtpVerifyResponseSerializer},
        examples=[
            OpenApiExample(
                "验证码登录",
                value={
                    "phone": "13900139000",
                    "code": "123456",
                    "tenant_slug": "acme",
                },
                request_only=True,
            ),
        ],
    )
    def post(self, request, *args, **kwargs):
        request_serializer = CustomerOtpVerifyRequestSerializer(data=request.data)
        request_serializer.is_valid(raise_exception=True)
        validated_data = request_serializer.validated_data

        try:
            tenant = Tenant.objects.get(slug=validated_data["tenant_slug"])
        except Tenant.DoesNotExist as exc:
            raise NotFound("租户不存在。") from exc
        if not tenant.is_active:
            raise ValidationError("租户已停用。")

        try:
            user = customer_authenticate(
                phone=validated_data["phone"],
                code=validated_data["code"],
                tenant=tenant,
            )
        except DjangoValidationError as exc:
            _raise_validation_error(exc)

        response_data = customer_tokens_issue(user=user)
        response_serializer = CustomerOtpVerifyResponseSerializer(response_data)
        return Response(response_serializer.data, status=status.HTTP_200_OK)
