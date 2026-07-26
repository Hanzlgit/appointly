from appointly.api.envelope import api_response
from appointly.api.openapi import enveloped_response_serializer
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.views import APIView

from tenants.models import Tenant
from tenants.permissions import (
    RequiresTenantAdmin,
    RequiresTenantCustomer,
    RequiresTenantMembership,
)
from tenants.selectors import (
    tenant_customer_me_get_for_user,
    tenant_get_by_slug,
    tenant_membership_role_get_for_user,
    tenant_scoped_record_list_for_tenant,
)
from tenants.serializers import (
    TenantContextRetrieveResponseSerializer,
    TenantCustomerMeRetrieveResponseSerializer,
    TenantMembershipRetrieveResponseSerializer,
    TenantScopedRecordCreateRequestSerializer,
    TenantScopedRecordCreateResponseSerializer,
    TenantScopedRecordListResponseSerializer,
    TenantScopedRecordResponseSerializer,
    TenantSettingsUpdateRequestSerializer,
    TenantSettingsUpdateResponseSerializer,
)
from tenants.services.tenant_scoped_record import tenant_scoped_record_create
from tenants.services.tenant_settings import tenant_timezone_update


class TenantContextMixin:
    tenant_lookup_url_kwarg = "tenant_slug"

    def get_tenant(self) -> Tenant:
        """从 URL slug 解析租户并缓存到 view 实例。

        Returns:
            Tenant: 路径对应的活跃租户。

        Raises:
            NotFound: slug 不存在。
            PermissionDenied: 租户已停用。
        """
        if hasattr(self, "_tenant"):
            return self._tenant

        slug = self.kwargs[self.tenant_lookup_url_kwarg]
        try:
            tenant = tenant_get_by_slug(slug=slug)
        except Tenant.DoesNotExist as exc:
            raise NotFound("租户不存在。") from exc

        if not tenant.is_active:
            raise PermissionDenied("租户已停用。")

        self._tenant = tenant
        return tenant


class TenantContextRetrieveView(TenantContextMixin, APIView):
    authentication_classes = []
    permission_classes = []

    @extend_schema(
        summary="获取租户公开信息",
        responses={200: enveloped_response_serializer(TenantContextRetrieveResponseSerializer)},
    )
    def get(self, request, *args, **kwargs):
        """返回租户公开上下文信息。

        Args:
            request: DRF 请求对象。

        Returns:
            Response: 含租户 slug、名称、时区等字段的标准 envelope 响应。
        """
        tenant = self.get_tenant()
        response_data = {
            "slug": tenant.slug,
            "name": tenant.name,
            "timezone": tenant.timezone,
            "is_active": tenant.is_active,
        }
        response_serializer = TenantContextRetrieveResponseSerializer(response_data)
        return api_response(request, data=response_serializer.data, status=status.HTTP_200_OK)


class TenantMembershipRetrieveView(TenantContextMixin, APIView):
    permission_classes = [RequiresTenantMembership]

    @extend_schema(
        summary="获取当前用户在租户下的角色",
        responses={200: enveloped_response_serializer(TenantMembershipRetrieveResponseSerializer)},
    )
    def get(self, request, *args, **kwargs):
        """返回当前用户在租户下的成员角色。

        Args:
            request: DRF 请求对象。

        Returns:
            Response: 含 ``role`` 字段的标准 envelope 响应。
        """
        tenant = self.get_tenant()
        role = tenant_membership_role_get_for_user(tenant=tenant, user=request.user)
        response_serializer = TenantMembershipRetrieveResponseSerializer({"role": role})
        return api_response(request, data=response_serializer.data, status=status.HTTP_200_OK)


class TenantScopedRecordListCreateView(TenantContextMixin, APIView):
    permission_classes = [RequiresTenantMembership, RequiresTenantAdmin]

    @extend_schema(
        summary="列出租户 scoped records",
        responses={200: enveloped_response_serializer(TenantScopedRecordListResponseSerializer)},
    )
    def get(self, request, *args, **kwargs):
        """列出租户下的 scoped records。

        Args:
            request: DRF 请求对象。

        Returns:
            Response: 含 ``records`` 列表的标准 envelope 响应。
        """
        tenant = self.get_tenant()
        records = tenant_scoped_record_list_for_tenant(tenant=tenant)
        response_serializer = TenantScopedRecordListResponseSerializer(
            {
                "records": TenantScopedRecordResponseSerializer(records, many=True).data,
            }
        )
        return api_response(request, data=response_serializer.data, status=status.HTTP_200_OK)

    @extend_schema(
        summary="创建租户 scoped record",
        request=TenantScopedRecordCreateRequestSerializer,
        responses={201: enveloped_response_serializer(TenantScopedRecordCreateResponseSerializer)},
    )
    def post(self, request, *args, **kwargs):
        """在租户下创建 scoped record。

        Args:
            request: DRF 请求对象。

        Returns:
            Response: 含新记录的标准 envelope 响应，HTTP 201。
        """
        tenant = self.get_tenant()
        request_serializer = TenantScopedRecordCreateRequestSerializer(data=request.data)
        request_serializer.is_valid(raise_exception=True)

        record = tenant_scoped_record_create(
            tenant=tenant,
            label=request_serializer.validated_data["label"],
        )
        response_serializer = TenantScopedRecordCreateResponseSerializer(record)
        return api_response(
            request,
            data=response_serializer.data,
            message="created",
            status=status.HTTP_201_CREATED,
        )


class TenantCustomerMeRetrieveView(TenantContextMixin, APIView):
    permission_classes = [RequiresTenantCustomer]

    @extend_schema(
        summary="获取当前客户在租户下的档案",
        responses={200: enveloped_response_serializer(TenantCustomerMeRetrieveResponseSerializer)},
    )
    def get(self, request, *args, **kwargs):
        """返回当前客户在租户下的档案信息。

        Args:
            request: DRF 请求对象。

        Returns:
            Response: 含客户档案字段的标准 envelope 响应。
        """
        tenant = self.get_tenant()
        response_data = tenant_customer_me_get_for_user(tenant=tenant, user=request.user)
        response_serializer = TenantCustomerMeRetrieveResponseSerializer(response_data)
        return api_response(request, data=response_serializer.data, status=status.HTTP_200_OK)


class TenantSettingsUpdateView(TenantContextMixin, APIView):
    permission_classes = [RequiresTenantMembership, RequiresTenantAdmin]

    @extend_schema(
        summary="更新租户设置",
        request=TenantSettingsUpdateRequestSerializer,
        responses={200: enveloped_response_serializer(TenantSettingsUpdateResponseSerializer)},
    )
    def patch(self, request, *args, **kwargs):
        """更新租户配置（如时区）。

        Args:
            request: DRF 请求对象。

        Returns:
            Response: 含更新后租户设置的标准 envelope 响应。
        """
        from django.core.exceptions import ValidationError as DjangoValidationError
        from rest_framework.exceptions import ValidationError as DRFValidationError

        tenant = self.get_tenant()
        request_serializer = TenantSettingsUpdateRequestSerializer(data=request.data, partial=True)
        request_serializer.is_valid(raise_exception=True)

        try:
            tenant = tenant_timezone_update(
                tenant=tenant,
                timezone=request_serializer.validated_data["timezone"],
            )
        except DjangoValidationError as exc:
            raise DRFValidationError(str(exc)) from exc

        response_data = {
            "slug": tenant.slug,
            "name": tenant.name,
            "timezone": tenant.timezone,
            "is_active": tenant.is_active,
        }
        response_serializer = TenantSettingsUpdateResponseSerializer(response_data)
        return api_response(request, data=response_serializer.data, status=status.HTTP_200_OK)
