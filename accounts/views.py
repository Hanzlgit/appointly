from appointly.api.envelope import api_response, build_envelope, request_id_from
from appointly.api.openapi import ApiEnvelopeWithNullDataSerializer, enveloped_response_serializer
from django.core.exceptions import ValidationError as DjangoValidationError
from drf_spectacular.utils import OpenApiExample, extend_schema
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenRefreshView as SimpleJwtTokenRefreshView

from accounts.serializers import (
    CustomerSessionCreateRequestSerializer,
    CustomerSessionCreateResponseSerializer,
    CustomerVerificationCodeCreateRequestSerializer,
    StaffSessionCreateRequestSerializer,
    StaffSessionCreateResponseSerializer,
    TokenRefreshRequestSerializer,
    TokenRefreshResponseSerializer,
)
from accounts.services.customer_auth import customer_authenticate, customer_tokens_issue
from accounts.services.otp import customer_otp_send
from accounts.services.staff_auth import staff_authenticate, staff_tokens_issue


def _raise_validation_error(exc: DjangoValidationError) -> None:
    """将 Django ValidationError 转为 DRF ValidationError。

    Args:
        exc (DjangoValidationError): Django 校验异常。

    Raises:
        ValidationError: 转换后的 DRF 校验异常。
    """
    if hasattr(exc, "message_dict"):
        raise ValidationError(exc.message_dict) from exc
    if hasattr(exc, "messages"):
        raise ValidationError(exc.messages) from exc
    raise ValidationError(str(exc)) from exc


class StaffSessionCreateView(APIView):
    authentication_classes = []
    permission_classes = []

    @extend_schema(
        summary="后台用户登录",
        description="使用用户名或手机号加密码登录，返回 access 与 refresh token。",
        request=StaffSessionCreateRequestSerializer,
        responses={200: enveloped_response_serializer(StaffSessionCreateResponseSerializer)},
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
        """后台用户密码登录并签发 JWT。

        Args:
            request: DRF 请求对象。

        Returns:
            Response: 含 access / refresh token 的标准 envelope 响应。
        """
        request_serializer = StaffSessionCreateRequestSerializer(data=request.data)
        request_serializer.is_valid(raise_exception=True)
        validated_data = request_serializer.validated_data

        try:
            user = staff_authenticate(
                login=validated_data["login"],
                password=validated_data["password"],
            )
        except DjangoValidationError as exc:
            _raise_validation_error(exc)

        response_data = staff_tokens_issue(user=user)
        response_serializer = StaffSessionCreateResponseSerializer(response_data)
        return api_response(request, data=response_serializer.data, status=status.HTTP_200_OK)


class CustomerVerificationCodeCreateView(APIView):
    authentication_classes = []
    permission_classes = []

    @extend_schema(
        summary="发送客户登录验证码",
        description="向手机号发送登录验证码（开发环境使用 Mock 短信适配器）。",
        request=CustomerVerificationCodeCreateRequestSerializer,
        responses={200: ApiEnvelopeWithNullDataSerializer},
        examples=[
            OpenApiExample(
                "发送验证码",
                value={"phone": "13900139000"},
                request_only=True,
            ),
        ],
    )
    def post(self, request, *args, **kwargs):
        """向客户手机号发送登录验证码。

        Args:
            request: DRF 请求对象。

        Returns:
            Response: 发送成功的标准 envelope 响应。
        """
        request_serializer = CustomerVerificationCodeCreateRequestSerializer(data=request.data)
        request_serializer.is_valid(raise_exception=True)

        try:
            customer_otp_send(phone=request_serializer.validated_data["phone"])
        except DjangoValidationError as exc:
            _raise_validation_error(exc)

        return api_response(request, data=None, message="验证码已发送。", status=status.HTTP_200_OK)


class CustomerSessionCreateView(APIView):
    authentication_classes = []
    permission_classes = []

    @extend_schema(
        summary="客户验证码登录",
        description="校验验证码并签发 JWT；首次验证自动创建平台账号，并确保租户客户档案存在。",
        request=CustomerSessionCreateRequestSerializer,
        responses={200: enveloped_response_serializer(CustomerSessionCreateResponseSerializer)},
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
        """校验验证码、建立客户档案并签发 JWT。

        Args:
            request: DRF 请求对象。

        Returns:
            Response: 含 access / refresh token 的标准 envelope 响应。
        """
        request_serializer = CustomerSessionCreateRequestSerializer(data=request.data)
        request_serializer.is_valid(raise_exception=True)
        validated_data = request_serializer.validated_data

        try:
            user = customer_authenticate(
                phone=validated_data["phone"],
                code=validated_data["code"],
                tenant_slug=validated_data["tenant_slug"],
            )
        except DjangoValidationError as exc:
            _raise_validation_error(exc)

        response_data = customer_tokens_issue(user=user)
        response_serializer = CustomerSessionCreateResponseSerializer(response_data)
        return api_response(request, data=response_serializer.data, status=status.HTTP_200_OK)


class TokenRefreshView(SimpleJwtTokenRefreshView):
    @extend_schema(
        summary="刷新 JWT",
        request=TokenRefreshRequestSerializer,
        responses={200: enveloped_response_serializer(TokenRefreshResponseSerializer)},
    )
    def post(self, request, *args, **kwargs):
        """刷新 JWT 并包装为标准 envelope 响应。

        Args:
            request: DRF 请求对象。

        Returns:
            Response: 含新 token 的标准 envelope 响应。
        """
        response = super().post(request, *args, **kwargs)
        request_id = request_id_from(request)
        if response.status_code >= 400:
            detail = response.data
            message = detail.get("detail", "请求失败") if isinstance(detail, dict) else str(detail)
            body = build_envelope(
                code=response.status_code,
                message=str(message),
                data=detail,
                request_id=request_id,
            )
            return Response(body, status=response.status_code)

        response_serializer = TokenRefreshResponseSerializer(response.data)
        return api_response(request, data=response_serializer.data, status=response.status_code)
