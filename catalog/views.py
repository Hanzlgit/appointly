from appointly.api.envelope import api_response
from appointly.api.openapi import enveloped_response_serializer
from django.core.exceptions import ValidationError as DjangoValidationError
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.exceptions import NotFound
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.response import Response
from rest_framework.views import APIView
from tenants.permissions import RequiresTenantAdmin, RequiresTenantMembership
from tenants.views import TenantContextMixin

from catalog.models import Location, Resource, Service
from catalog.selectors import (
    catalog_location_get_for_tenant,
    catalog_location_list_active_for_tenant,
    catalog_location_list_for_tenant,
    catalog_location_to_dict,
    catalog_public_location_to_dict,
    catalog_public_service_to_dict,
    catalog_resource_get_for_location,
    catalog_resource_list_for_location,
    catalog_resource_to_dict,
    catalog_service_get_for_location,
    catalog_service_list_active_for_tenant,
    catalog_service_list_for_location,
    catalog_service_to_dict,
)
from catalog.serializers import (
    CatalogLocationCreateRequestSerializer,
    CatalogLocationListResponseSerializer,
    CatalogLocationResponseSerializer,
    CatalogLocationUpdateRequestSerializer,
    CatalogPublicBrowseResponseSerializer,
    CatalogPublicLocationResponseSerializer,
    CatalogPublicServiceResponseSerializer,
    CatalogResourceCreateRequestSerializer,
    CatalogResourceListResponseSerializer,
    CatalogResourceResponseSerializer,
    CatalogResourceUpdateRequestSerializer,
    CatalogServiceCreateRequestSerializer,
    CatalogServiceListResponseSerializer,
    CatalogServiceResponseSerializer,
    CatalogServiceUpdateRequestSerializer,
)
from catalog.services.location import (
    catalog_location_create,
    catalog_location_delete,
    catalog_location_update,
)
from catalog.services.resource import (
    catalog_resource_create,
    catalog_resource_delete,
    catalog_resource_update,
)
from catalog.services.service import (
    catalog_service_create,
    catalog_service_delete,
    catalog_service_update,
)


def _raise_drf_validation_error(exc: DjangoValidationError) -> None:
    """将 Django ValidationError 转为 DRF ValidationError。

    Args:
        exc (DjangoValidationError): Django 校验异常。

    Raises:
        DRFValidationError: 含相同消息的 DRF 校验异常。
    """
    if hasattr(exc, "message_dict"):
        raise DRFValidationError(exc.message_dict) from exc
    if hasattr(exc, "messages"):
        raise DRFValidationError(exc.messages) from exc
    raise DRFValidationError(str(exc)) from exc


class CatalogLocationListCreateView(TenantContextMixin, APIView):
    permission_classes = [RequiresTenantMembership, RequiresTenantAdmin]

    @extend_schema(
        summary="列出服务地点",
        responses={200: enveloped_response_serializer(CatalogLocationListResponseSerializer)},
    )
    def get(self, request, *args, **kwargs):
        """列出租户下的服务地点。

        Args:
            request: DRF 请求对象。

        Returns:
            Response: 含 ``locations`` 列表的标准 envelope 响应。
        """
        tenant = self.get_tenant()
        locations = catalog_location_list_for_tenant(tenant=tenant)
        response_serializer = CatalogLocationListResponseSerializer(
            {
                "locations": [
                    CatalogLocationResponseSerializer(
                        catalog_location_to_dict(location=location)
                    ).data
                    for location in locations
                ],
            }
        )
        return api_response(request, data=response_serializer.data, status=status.HTTP_200_OK)

    @extend_schema(
        summary="创建服务地点",
        request=CatalogLocationCreateRequestSerializer,
        responses={201: enveloped_response_serializer(CatalogLocationResponseSerializer)},
    )
    def post(self, request, *args, **kwargs):
        """在租户下创建服务地点。

        Args:
            request: DRF 请求对象。

        Returns:
            Response: 含新地点的标准 envelope 响应，HTTP 201。
        """
        tenant = self.get_tenant()
        request_serializer = CatalogLocationCreateRequestSerializer(data=request.data)
        request_serializer.is_valid(raise_exception=True)
        validated_data = request_serializer.validated_data

        try:
            location = catalog_location_create(
                tenant=tenant,
                name=validated_data["name"],
                address=validated_data.get("address", ""),
            )
        except DjangoValidationError as exc:
            _raise_drf_validation_error(exc)

        response_serializer = CatalogLocationResponseSerializer(
            catalog_location_to_dict(location=location)
        )
        return api_response(
            request,
            data=response_serializer.data,
            message="created",
            status=status.HTTP_201_CREATED,
        )


class CatalogLocationRetrieveUpdateDestroyView(TenantContextMixin, APIView):
    permission_classes = [RequiresTenantMembership, RequiresTenantAdmin]

    def _get_location(self) -> Location:
        """从 URL 解析并返回当前租户下的地点。

        Returns:
            Location: 匹配的服务地点。

        Raises:
            NotFound: 地点不存在。
        """
        tenant = self.get_tenant()
        location_id = self.kwargs["location_id"]
        try:
            return catalog_location_get_for_tenant(tenant=tenant, location_id=location_id)
        except Location.DoesNotExist as exc:
            raise NotFound("服务地点不存在。") from exc

    @extend_schema(
        summary="获取服务地点",
        responses={200: enveloped_response_serializer(CatalogLocationResponseSerializer)},
    )
    def get(self, request, *args, **kwargs):
        """获取单个服务地点详情。

        Args:
            request: DRF 请求对象。

        Returns:
            Response: 含地点字段的标准 envelope 响应。
        """
        location = self._get_location()
        response_serializer = CatalogLocationResponseSerializer(
            catalog_location_to_dict(location=location)
        )
        return api_response(request, data=response_serializer.data, status=status.HTTP_200_OK)

    @extend_schema(
        summary="更新服务地点",
        request=CatalogLocationUpdateRequestSerializer,
        responses={200: enveloped_response_serializer(CatalogLocationResponseSerializer)},
    )
    def patch(self, request, *args, **kwargs):
        """部分更新服务地点。

        Args:
            request: DRF 请求对象。

        Returns:
            Response: 含更新后地点的标准 envelope 响应。
        """
        tenant = self.get_tenant()
        location = self._get_location()
        request_serializer = CatalogLocationUpdateRequestSerializer(data=request.data, partial=True)
        request_serializer.is_valid(raise_exception=True)
        validated_data = request_serializer.validated_data

        try:
            location = catalog_location_update(
                tenant=tenant,
                location=location,
                name=validated_data.get("name"),
                address=validated_data.get("address"),
                is_active=validated_data.get("is_active"),
            )
        except DjangoValidationError as exc:
            _raise_drf_validation_error(exc)

        response_serializer = CatalogLocationResponseSerializer(
            catalog_location_to_dict(location=location)
        )
        return api_response(request, data=response_serializer.data, status=status.HTTP_200_OK)

    @extend_schema(summary="删除服务地点", responses={204: None})
    def delete(self, request, *args, **kwargs):
        """物理删除未被引用的服务地点。

        Args:
            request: DRF 请求对象。

        Returns:
            Response: HTTP 204 空响应。
        """
        tenant = self.get_tenant()
        location = self._get_location()
        try:
            catalog_location_delete(tenant=tenant, location=location)
        except DjangoValidationError as exc:
            _raise_drf_validation_error(exc)
        return Response(status=status.HTTP_204_NO_CONTENT)


class CatalogLocationResourceListCreateView(TenantContextMixin, APIView):
    permission_classes = [RequiresTenantMembership, RequiresTenantAdmin]

    def _get_location(self) -> Location:
        """从 URL 解析并返回当前租户下的地点。

        Returns:
            Location: 匹配的服务地点。

        Raises:
            NotFound: 地点不存在。
        """
        tenant = self.get_tenant()
        location_id = self.kwargs["location_id"]
        try:
            return catalog_location_get_for_tenant(tenant=tenant, location_id=location_id)
        except Location.DoesNotExist as exc:
            raise NotFound("服务地点不存在。") from exc

    @extend_schema(
        summary="列出地点下的可预约资源",
        responses={200: enveloped_response_serializer(CatalogResourceListResponseSerializer)},
    )
    def get(self, request, *args, **kwargs):
        """列出指定地点下的可预约资源。

        Args:
            request: DRF 请求对象。

        Returns:
            Response: 含 ``resources`` 列表的标准 envelope 响应。
        """
        location = self._get_location()
        resources = catalog_resource_list_for_location(location=location)
        response_serializer = CatalogResourceListResponseSerializer(
            {
                "resources": [
                    CatalogResourceResponseSerializer(
                        catalog_resource_to_dict(resource=resource)
                    ).data
                    for resource in resources
                ],
            }
        )
        return api_response(request, data=response_serializer.data, status=status.HTTP_200_OK)

    @extend_schema(
        summary="在地点下创建可预约资源",
        request=CatalogResourceCreateRequestSerializer,
        responses={201: enveloped_response_serializer(CatalogResourceResponseSerializer)},
    )
    def post(self, request, *args, **kwargs):
        """在指定地点下创建可预约资源。

        Args:
            request: DRF 请求对象。

        Returns:
            Response: 含新资源的标准 envelope 响应，HTTP 201。
        """
        tenant = self.get_tenant()
        location = self._get_location()
        request_serializer = CatalogResourceCreateRequestSerializer(data=request.data)
        request_serializer.is_valid(raise_exception=True)
        validated_data = request_serializer.validated_data

        try:
            resource = catalog_resource_create(
                tenant=tenant,
                location=location,
                name=validated_data["name"],
            )
        except DjangoValidationError as exc:
            _raise_drf_validation_error(exc)

        response_serializer = CatalogResourceResponseSerializer(
            catalog_resource_to_dict(resource=resource)
        )
        return api_response(
            request,
            data=response_serializer.data,
            message="created",
            status=status.HTTP_201_CREATED,
        )


class CatalogLocationResourceRetrieveUpdateDestroyView(TenantContextMixin, APIView):
    permission_classes = [RequiresTenantMembership, RequiresTenantAdmin]

    def _get_location(self) -> Location:
        """从 URL 解析并返回当前租户下的地点。

        Returns:
            Location: 匹配的服务地点。

        Raises:
            NotFound: 地点不存在。
        """
        tenant = self.get_tenant()
        location_id = self.kwargs["location_id"]
        try:
            return catalog_location_get_for_tenant(tenant=tenant, location_id=location_id)
        except Location.DoesNotExist as exc:
            raise NotFound("服务地点不存在。") from exc

    def _get_resource(self, *, location: Location) -> Resource:
        """从 URL 解析并返回指定地点下的资源。

        Args:
            location (Location): 所属地点。

        Returns:
            Resource: 匹配的可预约资源。

        Raises:
            NotFound: 资源不存在。
        """
        tenant = self.get_tenant()
        resource_id = self.kwargs["resource_id"]
        try:
            return catalog_resource_get_for_location(
                tenant=tenant,
                location=location,
                resource_id=resource_id,
            )
        except Resource.DoesNotExist as exc:
            raise NotFound("可预约资源不存在。") from exc

    @extend_schema(
        summary="获取地点下的可预约资源",
        responses={200: enveloped_response_serializer(CatalogResourceResponseSerializer)},
    )
    def get(self, request, *args, **kwargs):
        """获取指定地点下的单个可预约资源。

        Args:
            request: DRF 请求对象。

        Returns:
            Response: 含资源字段的标准 envelope 响应。
        """
        location = self._get_location()
        resource = self._get_resource(location=location)
        response_serializer = CatalogResourceResponseSerializer(
            catalog_resource_to_dict(resource=resource)
        )
        return api_response(request, data=response_serializer.data, status=status.HTTP_200_OK)

    @extend_schema(
        summary="更新地点下的可预约资源",
        request=CatalogResourceUpdateRequestSerializer,
        responses={200: enveloped_response_serializer(CatalogResourceResponseSerializer)},
    )
    def patch(self, request, *args, **kwargs):
        """部分更新指定地点下的可预约资源。

        Args:
            request: DRF 请求对象。

        Returns:
            Response: 含更新后资源的标准 envelope 响应。
        """
        tenant = self.get_tenant()
        location = self._get_location()
        resource = self._get_resource(location=location)
        request_serializer = CatalogResourceUpdateRequestSerializer(data=request.data, partial=True)
        request_serializer.is_valid(raise_exception=True)
        validated_data = request_serializer.validated_data

        try:
            resource = catalog_resource_update(
                tenant=tenant,
                resource=resource,
                name=validated_data.get("name"),
                is_active=validated_data.get("is_active"),
            )
        except DjangoValidationError as exc:
            _raise_drf_validation_error(exc)

        response_serializer = CatalogResourceResponseSerializer(
            catalog_resource_to_dict(resource=resource)
        )
        return api_response(request, data=response_serializer.data, status=status.HTTP_200_OK)

    @extend_schema(summary="删除地点下的可预约资源", responses={204: None})
    def delete(self, request, *args, **kwargs):
        """物理删除指定地点下未被引用的可预约资源。

        Args:
            request: DRF 请求对象。

        Returns:
            Response: HTTP 204 空响应。
        """
        tenant = self.get_tenant()
        location = self._get_location()
        resource = self._get_resource(location=location)
        try:
            catalog_resource_delete(tenant=tenant, resource=resource)
        except DjangoValidationError as exc:
            _raise_drf_validation_error(exc)
        return Response(status=status.HTTP_204_NO_CONTENT)


class CatalogLocationServiceListCreateView(TenantContextMixin, APIView):
    permission_classes = [RequiresTenantMembership, RequiresTenantAdmin]

    def _get_location(self) -> Location:
        """从 URL 解析并返回当前租户下的地点。

        Returns:
            Location: 匹配的服务地点。

        Raises:
            NotFound: 地点不存在。
        """
        tenant = self.get_tenant()
        location_id = self.kwargs["location_id"]
        try:
            return catalog_location_get_for_tenant(tenant=tenant, location_id=location_id)
        except Location.DoesNotExist as exc:
            raise NotFound("服务地点不存在。") from exc

    @extend_schema(
        summary="列出地点下的服务项目",
        responses={200: enveloped_response_serializer(CatalogServiceListResponseSerializer)},
    )
    def get(self, request, *args, **kwargs):
        """列出指定地点下的服务项目。

        Args:
            request: DRF 请求对象。

        Returns:
            Response: 含 ``services`` 列表的标准 envelope 响应。
        """
        location = self._get_location()
        services = catalog_service_list_for_location(location=location)
        response_serializer = CatalogServiceListResponseSerializer(
            {
                "services": [
                    CatalogServiceResponseSerializer(catalog_service_to_dict(service=service)).data
                    for service in services
                ],
            }
        )
        return api_response(request, data=response_serializer.data, status=status.HTTP_200_OK)

    @extend_schema(
        summary="在地点下创建服务项目",
        request=CatalogServiceCreateRequestSerializer,
        responses={201: enveloped_response_serializer(CatalogServiceResponseSerializer)},
    )
    def post(self, request, *args, **kwargs):
        """在指定地点下创建服务项目。

        Args:
            request: DRF 请求对象。

        Returns:
            Response: 含新服务的标准 envelope 响应，HTTP 201。
        """
        tenant = self.get_tenant()
        location = self._get_location()
        request_serializer = CatalogServiceCreateRequestSerializer(data=request.data)
        request_serializer.is_valid(raise_exception=True)
        validated_data = request_serializer.validated_data

        try:
            service = catalog_service_create(
                tenant=tenant,
                location=location,
                name=validated_data["name"],
                description=validated_data.get("description", ""),
                duration_minutes=validated_data["duration_minutes"],
                price_cents=validated_data.get("price_cents", 0),
                currency=validated_data.get("currency", "CNY"),
                resource_ids=validated_data.get("resource_ids"),
            )
        except DjangoValidationError as exc:
            _raise_drf_validation_error(exc)

        response_serializer = CatalogServiceResponseSerializer(
            catalog_service_to_dict(service=service)
        )
        return api_response(
            request,
            data=response_serializer.data,
            message="created",
            status=status.HTTP_201_CREATED,
        )


class CatalogLocationServiceRetrieveUpdateDestroyView(TenantContextMixin, APIView):
    permission_classes = [RequiresTenantMembership, RequiresTenantAdmin]

    def _get_location(self) -> Location:
        """从 URL 解析并返回当前租户下的地点。

        Returns:
            Location: 匹配的服务地点。

        Raises:
            NotFound: 地点不存在。
        """
        tenant = self.get_tenant()
        location_id = self.kwargs["location_id"]
        try:
            return catalog_location_get_for_tenant(tenant=tenant, location_id=location_id)
        except Location.DoesNotExist as exc:
            raise NotFound("服务地点不存在。") from exc

    def _get_service(self, *, location: Location) -> Service:
        """从 URL 解析并返回指定地点下的服务。

        Args:
            location (Location): 所属地点。

        Returns:
            Service: 匹配的服务项目。

        Raises:
            NotFound: 服务不存在。
        """
        tenant = self.get_tenant()
        service_id = self.kwargs["service_id"]
        try:
            return catalog_service_get_for_location(
                tenant=tenant,
                location=location,
                service_id=service_id,
            )
        except Service.DoesNotExist as exc:
            raise NotFound("服务项目不存在。") from exc

    @extend_schema(
        summary="获取地点下的服务项目",
        responses={200: enveloped_response_serializer(CatalogServiceResponseSerializer)},
    )
    def get(self, request, *args, **kwargs):
        """获取指定地点下的单个服务项目。

        Args:
            request: DRF 请求对象。

        Returns:
            Response: 含服务字段的标准 envelope 响应。
        """
        location = self._get_location()
        service = self._get_service(location=location)
        response_serializer = CatalogServiceResponseSerializer(
            catalog_service_to_dict(service=service)
        )
        return api_response(request, data=response_serializer.data, status=status.HTTP_200_OK)

    @extend_schema(
        summary="更新地点下的服务项目",
        request=CatalogServiceUpdateRequestSerializer,
        responses={200: enveloped_response_serializer(CatalogServiceResponseSerializer)},
    )
    def patch(self, request, *args, **kwargs):
        """部分更新指定地点下的服务项目。

        Args:
            request: DRF 请求对象。

        Returns:
            Response: 含更新后服务的标准 envelope 响应。
        """
        tenant = self.get_tenant()
        location = self._get_location()
        service = self._get_service(location=location)
        request_serializer = CatalogServiceUpdateRequestSerializer(data=request.data, partial=True)
        request_serializer.is_valid(raise_exception=True)
        validated_data = request_serializer.validated_data

        try:
            service = catalog_service_update(
                tenant=tenant,
                service=service,
                name=validated_data.get("name"),
                description=validated_data.get("description"),
                duration_minutes=validated_data.get("duration_minutes"),
                price_cents=validated_data.get("price_cents"),
                currency=validated_data.get("currency"),
                is_active=validated_data.get("is_active"),
                resource_ids=validated_data.get("resource_ids"),
            )
        except DjangoValidationError as exc:
            _raise_drf_validation_error(exc)

        response_serializer = CatalogServiceResponseSerializer(
            catalog_service_to_dict(service=service)
        )
        return api_response(request, data=response_serializer.data, status=status.HTTP_200_OK)

    @extend_schema(summary="删除地点下的服务项目", responses={204: None})
    def delete(self, request, *args, **kwargs):
        """物理删除指定地点下未被引用的服务项目。

        Args:
            request: DRF 请求对象。

        Returns:
            Response: HTTP 204 空响应。
        """
        tenant = self.get_tenant()
        location = self._get_location()
        service = self._get_service(location=location)
        try:
            catalog_service_delete(tenant=tenant, service=service)
        except DjangoValidationError as exc:
            _raise_drf_validation_error(exc)
        return Response(status=status.HTTP_204_NO_CONTENT)


class CatalogPublicBrowseView(TenantContextMixin, APIView):
    authentication_classes = []
    permission_classes = []

    @extend_schema(
        summary="浏览公开目录",
        responses={200: enveloped_response_serializer(CatalogPublicBrowseResponseSerializer)},
    )
    def get(self, request, *args, **kwargs):
        """返回租户启用的公开地点与服务目录。

        Args:
            request: DRF 请求对象。

        Returns:
            Response: 含 ``locations`` 与 ``services`` 的标准 envelope 响应。
        """
        tenant = self.get_tenant()
        locations = catalog_location_list_active_for_tenant(tenant=tenant)
        services = catalog_service_list_active_for_tenant(tenant=tenant)
        response_serializer = CatalogPublicBrowseResponseSerializer(
            {
                "locations": [
                    CatalogPublicLocationResponseSerializer(
                        catalog_public_location_to_dict(location=location)
                    ).data
                    for location in locations
                ],
                "services": [
                    CatalogPublicServiceResponseSerializer(
                        catalog_public_service_to_dict(service=service)
                    ).data
                    for service in services
                ],
            }
        )
        return api_response(request, data=response_serializer.data, status=status.HTTP_200_OK)
