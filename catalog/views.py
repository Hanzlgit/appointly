from accounts.permissions import RequiresStaff
from appointly.api.envelope import api_response
from appointly.api.openapi import enveloped_response_serializer
from django.core.exceptions import ValidationError as DjangoValidationError
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.exceptions import NotFound
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from catalog.models import Location, Service, Stylist
from catalog.selectors import (
    catalog_location_get,
    catalog_location_list_paginated,
    catalog_location_to_dict,
    catalog_public_location_to_dict,
    catalog_public_service_to_dict,
    catalog_public_stylist_to_dict,
    catalog_service_get_for_stylist,
    catalog_service_list_for_stylist_paginated,
    catalog_service_to_dict,
    catalog_stylist_get,
    catalog_stylist_get_for_location,
    catalog_stylist_list_for_location_paginated,
    catalog_stylist_to_dict,
)
from catalog.serializers import (
    CatalogListQuerySerializer,
    CatalogLocationCreateRequestSerializer,
    CatalogLocationResponseSerializer,
    CatalogLocationUpdateRequestSerializer,
    CatalogPaginatedLocationListResponseSerializer,
    CatalogPaginatedPublicLocationListResponseSerializer,
    CatalogPaginatedPublicStylistListResponseSerializer,
    CatalogPaginatedPublicServiceListResponseSerializer,
    CatalogPaginatedServiceListResponseSerializer,
    CatalogPaginatedStylistListResponseSerializer,
    CatalogPublicLocationResponseSerializer,
    CatalogPublicServiceResponseSerializer,
    CatalogPublicStylistResponseSerializer,
    CatalogServiceCreateRequestSerializer,
    CatalogServiceResponseSerializer,
    CatalogServiceUpdateRequestSerializer,
    CatalogStylistCreateRequestSerializer,
    CatalogStylistResponseSerializer,
    CatalogStylistUpdateRequestSerializer,
)
from catalog.services.location import (
    catalog_location_create,
    catalog_location_delete,
    catalog_location_update,
)
from catalog.services.service import (
    catalog_service_create,
    catalog_service_delete,
    catalog_service_update,
)
from catalog.services.stylist import (
    catalog_stylist_create,
    catalog_stylist_delete,
    catalog_stylist_update,
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


def _request_is_staff(request) -> bool:
    """判断请求是否来自后台工作人员。

    Args:
        request: DRF 请求对象。

    Returns:
        bool: 工作人员或超管时返回 ``True``。
    """
    user = request.user
    return bool(
        user
        and user.is_authenticated
        and (user.is_superuser or hasattr(user, "staff_profile")),
    )


def _parse_list_query(request) -> dict:
    """解析并校验列表查询参数。

    Args:
        request: DRF 请求对象。

    Returns:
        dict: 校验后的 ``page``、``page_size``、``q`` 字段。
    """
    query_serializer = CatalogListQuerySerializer(data=request.query_params)
    query_serializer.is_valid(raise_exception=True)
    return query_serializer.validated_data


class CatalogLocationListCreateView(APIView):
    """门店列表（公开）与创建（后台）。"""

    def get_permissions(self):
        """按 HTTP 方法返回权限类。

        Returns:
            list: POST 需工作人员权限，GET 公开。
        """
        if self.request.method == "POST":
            return [RequiresStaff()]
        return []

    @extend_schema(
        summary="列出门店",
        parameters=[CatalogListQuerySerializer],
        responses={
            200: enveloped_response_serializer(CatalogPaginatedPublicLocationListResponseSerializer),
        },
    )
    def get(self, request, *args, **kwargs):
        """公开列出启用门店；工作人员可查看全部门店。

        Args:
            request: DRF 请求对象。

        Returns:
            Response: 分页门店列表 envelope 响应。
        """
        validated = _parse_list_query(request)
        is_staff = _request_is_staff(request)
        result = catalog_location_list_paginated(
            page=validated["page"],
            page_size=validated["page_size"],
            q=validated["q"],
            active_only=not is_staff,
        )

        if is_staff:
            response_serializer = CatalogPaginatedLocationListResponseSerializer(
                {
                    "items": [
                        CatalogLocationResponseSerializer(catalog_location_to_dict(location=item)).data
                        for item in result.items
                    ],
                    "total": result.total,
                    "page": validated["page"],
                    "page_size": validated["page_size"],
                }
            )
        else:
            response_serializer = CatalogPaginatedPublicLocationListResponseSerializer(
                {
                    "items": [
                        CatalogPublicLocationResponseSerializer(
                            catalog_public_location_to_dict(location=item)
                        ).data
                        for item in result.items
                    ],
                    "total": result.total,
                    "page": validated["page"],
                    "page_size": validated["page_size"],
                }
            )
        return api_response(request, data=response_serializer.data, status=status.HTTP_200_OK)

    @extend_schema(
        summary="创建门店",
        request=CatalogLocationCreateRequestSerializer,
        responses={201: enveloped_response_serializer(CatalogLocationResponseSerializer)},
    )
    def post(self, request, *args, **kwargs):
        """创建门店。

        Args:
            request: DRF 请求对象。

        Returns:
            Response: 含新门店的标准 envelope 响应，HTTP 201。
        """
        request_serializer = CatalogLocationCreateRequestSerializer(data=request.data)
        request_serializer.is_valid(raise_exception=True)
        validated_data = request_serializer.validated_data

        try:
            location = catalog_location_create(
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


class CatalogLocationRetrieveUpdateDestroyView(APIView):
    """门店详情、更新与删除（后台）。"""

    permission_classes = [RequiresStaff]

    def _get_location(self) -> Location:
        """从 URL 解析并返回门店。

        Returns:
            Location: 匹配的门店。

        Raises:
            NotFound: 门店不存在。
        """
        location_id = self.kwargs["location_id"]
        try:
            return catalog_location_get(location_id=location_id)
        except Location.DoesNotExist as exc:
            raise NotFound("门店不存在。") from exc

    @extend_schema(
        summary="获取门店",
        responses={200: enveloped_response_serializer(CatalogLocationResponseSerializer)},
    )
    def get(self, request, *args, **kwargs):
        """获取单个门店详情。

        Args:
            request: DRF 请求对象。

        Returns:
            Response: 含门店字段的标准 envelope 响应。
        """
        location = self._get_location()
        response_serializer = CatalogLocationResponseSerializer(
            catalog_location_to_dict(location=location)
        )
        return api_response(request, data=response_serializer.data, status=status.HTTP_200_OK)

    @extend_schema(
        summary="更新门店",
        request=CatalogLocationUpdateRequestSerializer,
        responses={200: enveloped_response_serializer(CatalogLocationResponseSerializer)},
    )
    def patch(self, request, *args, **kwargs):
        """部分更新门店。

        Args:
            request: DRF 请求对象。

        Returns:
            Response: 含更新后门店的标准 envelope 响应。
        """
        location = self._get_location()
        request_serializer = CatalogLocationUpdateRequestSerializer(data=request.data, partial=True)
        request_serializer.is_valid(raise_exception=True)
        validated_data = request_serializer.validated_data

        try:
            location = catalog_location_update(
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

    @extend_schema(summary="删除门店", responses={204: None})
    def delete(self, request, *args, **kwargs):
        """物理删除未被引用的门店。

        Args:
            request: DRF 请求对象。

        Returns:
            Response: HTTP 204 空响应。
        """
        location = self._get_location()
        try:
            catalog_location_delete(location=location)
        except DjangoValidationError as exc:
            _raise_drf_validation_error(exc)
        return Response(status=status.HTTP_204_NO_CONTENT)


class CatalogLocationStylistListCreateView(APIView):
    """门店理发师列表（公开）与创建（后台）。"""

    def get_permissions(self):
        """按 HTTP 方法返回权限类。

        Returns:
            list: POST 需工作人员权限，GET 公开。
        """
        if self.request.method == "POST":
            return [RequiresStaff()]
        return []

    def _get_location(self) -> Location:
        """从 URL 解析并返回门店。

        Returns:
            Location: 匹配的门店。

        Raises:
            NotFound: 门店不存在。
        """
        location_id = self.kwargs["location_id"]
        try:
            return catalog_location_get(location_id=location_id)
        except Location.DoesNotExist as exc:
            raise NotFound("门店不存在。") from exc

    @extend_schema(
        summary="列出门店下的理发师",
        parameters=[CatalogListQuerySerializer],
        responses={
            200: enveloped_response_serializer(CatalogPaginatedPublicStylistListResponseSerializer),
        },
    )
    def get(self, request, *args, **kwargs):
        """公开列出启用理发师；工作人员可查看全部。

        Args:
            request: DRF 请求对象。

        Returns:
            Response: 分页理发师列表 envelope 响应。
        """
        location = self._get_location()
        validated = _parse_list_query(request)
        is_staff = _request_is_staff(request)
        result = catalog_stylist_list_for_location_paginated(
            location=location,
            page=validated["page"],
            page_size=validated["page_size"],
            q=validated["q"],
            active_only=not is_staff,
        )

        if is_staff:
            response_serializer = CatalogPaginatedStylistListResponseSerializer(
                {
                    "items": [
                        CatalogStylistResponseSerializer(catalog_stylist_to_dict(stylist=item)).data
                        for item in result.items
                    ],
                    "total": result.total,
                    "page": validated["page"],
                    "page_size": validated["page_size"],
                }
            )
        else:
            response_serializer = CatalogPaginatedPublicStylistListResponseSerializer(
                {
                    "items": [
                        CatalogPublicStylistResponseSerializer(
                            catalog_public_stylist_to_dict(stylist=item)
                        ).data
                        for item in result.items
                    ],
                    "total": result.total,
                    "page": validated["page"],
                    "page_size": validated["page_size"],
                }
            )
        return api_response(request, data=response_serializer.data, status=status.HTTP_200_OK)

    @extend_schema(
        summary="在门店下创建理发师",
        request=CatalogStylistCreateRequestSerializer,
        responses={201: enveloped_response_serializer(CatalogStylistResponseSerializer)},
    )
    def post(self, request, *args, **kwargs):
        """在指定门店下创建理发师。

        Args:
            request: DRF 请求对象。

        Returns:
            Response: 含新理发师的标准 envelope 响应，HTTP 201。
        """
        location = self._get_location()
        request_serializer = CatalogStylistCreateRequestSerializer(data=request.data)
        request_serializer.is_valid(raise_exception=True)
        validated_data = request_serializer.validated_data

        try:
            stylist = catalog_stylist_create(
                location=location,
                name=validated_data["name"],
                ticket_prefix=validated_data.get("ticket_prefix", ""),
                queue_status=validated_data.get("queue_status"),
            )
        except DjangoValidationError as exc:
            _raise_drf_validation_error(exc)

        response_serializer = CatalogStylistResponseSerializer(
            catalog_stylist_to_dict(stylist=stylist)
        )
        return api_response(
            request,
            data=response_serializer.data,
            message="created",
            status=status.HTTP_201_CREATED,
        )


class CatalogLocationStylistRetrieveUpdateDestroyView(APIView):
    """门店理发师详情、更新与删除（后台）。"""

    permission_classes = [RequiresStaff]

    def _get_location(self) -> Location:
        """从 URL 解析并返回门店。

        Returns:
            Location: 匹配的门店。

        Raises:
            NotFound: 门店不存在。
        """
        location_id = self.kwargs["location_id"]
        try:
            return catalog_location_get(location_id=location_id)
        except Location.DoesNotExist as exc:
            raise NotFound("门店不存在。") from exc

    def _get_stylist(self, *, location: Location) -> Stylist:
        """从 URL 解析并返回指定门店下的理发师。

        Args:
            location (Location): 所属门店。

        Returns:
            Stylist: 匹配的理发师。

        Raises:
            NotFound: 理发师不存在。
        """
        stylist_id = self.kwargs["stylist_id"]
        try:
            return catalog_stylist_get_for_location(location=location, stylist_id=stylist_id)
        except Stylist.DoesNotExist as exc:
            raise NotFound("理发师不存在。") from exc

    @extend_schema(
        summary="获取门店下的理发师",
        responses={200: enveloped_response_serializer(CatalogStylistResponseSerializer)},
    )
    def get(self, request, *args, **kwargs):
        """获取指定门店下的单个理发师。

        Args:
            request: DRF 请求对象。

        Returns:
            Response: 含理发师字段的标准 envelope 响应。
        """
        location = self._get_location()
        stylist = self._get_stylist(location=location)
        response_serializer = CatalogStylistResponseSerializer(
            catalog_stylist_to_dict(stylist=stylist)
        )
        return api_response(request, data=response_serializer.data, status=status.HTTP_200_OK)

    @extend_schema(
        summary="更新门店下的理发师",
        request=CatalogStylistUpdateRequestSerializer,
        responses={200: enveloped_response_serializer(CatalogStylistResponseSerializer)},
    )
    def patch(self, request, *args, **kwargs):
        """部分更新指定门店下的理发师。

        Args:
            request: DRF 请求对象。

        Returns:
            Response: 含更新后理发师的标准 envelope 响应。
        """
        location = self._get_location()
        stylist = self._get_stylist(location=location)
        request_serializer = CatalogStylistUpdateRequestSerializer(data=request.data, partial=True)
        request_serializer.is_valid(raise_exception=True)
        validated_data = request_serializer.validated_data

        try:
            stylist = catalog_stylist_update(
                stylist=stylist,
                name=validated_data.get("name"),
                ticket_prefix=validated_data.get("ticket_prefix"),
                queue_status=validated_data.get("queue_status"),
                is_active=validated_data.get("is_active"),
            )
        except DjangoValidationError as exc:
            _raise_drf_validation_error(exc)

        response_serializer = CatalogStylistResponseSerializer(
            catalog_stylist_to_dict(stylist=stylist)
        )
        return api_response(request, data=response_serializer.data, status=status.HTTP_200_OK)

    @extend_schema(summary="删除门店下的理发师", responses={204: None})
    def delete(self, request, *args, **kwargs):
        """物理删除指定门店下未被引用的理发师。

        Args:
            request: DRF 请求对象。

        Returns:
            Response: HTTP 204 空响应。
        """
        location = self._get_location()
        stylist = self._get_stylist(location=location)
        try:
            catalog_stylist_delete(stylist=stylist)
        except DjangoValidationError as exc:
            _raise_drf_validation_error(exc)
        return Response(status=status.HTTP_204_NO_CONTENT)


class CatalogStylistServiceListCreateView(APIView):
    """理发师服务项目列表（公开）与创建（后台）。"""

    def get_permissions(self):
        """按 HTTP 方法返回权限类。

        Returns:
            list: POST 需工作人员权限，GET 公开。
        """
        if self.request.method == "POST":
            return [RequiresStaff()]
        return []

    def _get_stylist(self) -> Stylist:
        """从 URL 解析并返回理发师。

        Returns:
            Stylist: 匹配的理发师。

        Raises:
            NotFound: 理发师不存在。
        """
        stylist_id = self.kwargs["stylist_id"]
        try:
            return catalog_stylist_get(stylist_id=stylist_id)
        except Stylist.DoesNotExist as exc:
            raise NotFound("理发师不存在。") from exc

    @extend_schema(
        summary="列出理发师下的服务项目",
        parameters=[CatalogListQuerySerializer],
        responses={
            200: enveloped_response_serializer(CatalogPaginatedPublicServiceListResponseSerializer),
        },
    )
    def get(self, request, *args, **kwargs):
        """公开列出启用服务；工作人员可查看全部。

        Args:
            request: DRF 请求对象。

        Returns:
            Response: 分页服务列表 envelope 响应。
        """
        stylist = self._get_stylist()
        validated = _parse_list_query(request)
        is_staff = _request_is_staff(request)
        result = catalog_service_list_for_stylist_paginated(
            stylist=stylist,
            page=validated["page"],
            page_size=validated["page_size"],
            q=validated["q"],
            active_only=not is_staff,
        )

        if is_staff:
            response_serializer = CatalogPaginatedServiceListResponseSerializer(
                {
                    "items": [
                        CatalogServiceResponseSerializer(catalog_service_to_dict(service=item)).data
                        for item in result.items
                    ],
                    "total": result.total,
                    "page": validated["page"],
                    "page_size": validated["page_size"],
                }
            )
        else:
            response_serializer = CatalogPaginatedPublicServiceListResponseSerializer(
                {
                    "items": [
                        CatalogPublicServiceResponseSerializer(
                            catalog_public_service_to_dict(service=item)
                        ).data
                        for item in result.items
                    ],
                    "total": result.total,
                    "page": validated["page"],
                    "page_size": validated["page_size"],
                }
            )
        return api_response(request, data=response_serializer.data, status=status.HTTP_200_OK)

    @extend_schema(
        summary="在理发师下创建服务项目",
        request=CatalogServiceCreateRequestSerializer,
        responses={201: enveloped_response_serializer(CatalogServiceResponseSerializer)},
    )
    def post(self, request, *args, **kwargs):
        """在指定理发师下创建服务项目。

        Args:
            request: DRF 请求对象。

        Returns:
            Response: 含新服务的标准 envelope 响应，HTTP 201。
        """
        stylist = self._get_stylist()
        request_serializer = CatalogServiceCreateRequestSerializer(data=request.data)
        request_serializer.is_valid(raise_exception=True)
        validated_data = request_serializer.validated_data

        try:
            service = catalog_service_create(
                stylist=stylist,
                name=validated_data["name"],
                description=validated_data.get("description", ""),
                duration_minutes=validated_data["duration_minutes"],
                price_cents=validated_data.get("price_cents", 0),
                currency=validated_data.get("currency", "CNY"),
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


class CatalogStylistServiceRetrieveUpdateDestroyView(APIView):
    """理发师服务项目详情、更新与删除（后台）。"""

    permission_classes = [RequiresStaff]

    def _get_stylist(self) -> Stylist:
        """从 URL 解析并返回理发师。

        Returns:
            Stylist: 匹配的理发师。

        Raises:
            NotFound: 理发师不存在。
        """
        stylist_id = self.kwargs["stylist_id"]
        try:
            return catalog_stylist_get(stylist_id=stylist_id)
        except Stylist.DoesNotExist as exc:
            raise NotFound("理发师不存在。") from exc

    def _get_service(self, *, stylist: Stylist) -> Service:
        """从 URL 解析并返回指定理发师下的服务。

        Args:
            stylist (Stylist): 所属理发师。

        Returns:
            Service: 匹配的服务项目。

        Raises:
            NotFound: 服务不存在。
        """
        service_id = self.kwargs["service_id"]
        try:
            return catalog_service_get_for_stylist(stylist=stylist, service_id=service_id)
        except Service.DoesNotExist as exc:
            raise NotFound("服务项目不存在。") from exc

    @extend_schema(
        summary="获取理发师下的服务项目",
        responses={200: enveloped_response_serializer(CatalogServiceResponseSerializer)},
    )
    def get(self, request, *args, **kwargs):
        """获取指定理发师下的单个服务项目。

        Args:
            request: DRF 请求对象。

        Returns:
            Response: 含服务字段的标准 envelope 响应。
        """
        stylist = self._get_stylist()
        service = self._get_service(stylist=stylist)
        response_serializer = CatalogServiceResponseSerializer(
            catalog_service_to_dict(service=service)
        )
        return api_response(request, data=response_serializer.data, status=status.HTTP_200_OK)

    @extend_schema(
        summary="更新理发师下的服务项目",
        request=CatalogServiceUpdateRequestSerializer,
        responses={200: enveloped_response_serializer(CatalogServiceResponseSerializer)},
    )
    def patch(self, request, *args, **kwargs):
        """部分更新指定理发师下的服务项目。

        Args:
            request: DRF 请求对象。

        Returns:
            Response: 含更新后服务的标准 envelope 响应。
        """
        stylist = self._get_stylist()
        service = self._get_service(stylist=stylist)
        request_serializer = CatalogServiceUpdateRequestSerializer(data=request.data, partial=True)
        request_serializer.is_valid(raise_exception=True)
        validated_data = request_serializer.validated_data

        try:
            service = catalog_service_update(
                service=service,
                name=validated_data.get("name"),
                description=validated_data.get("description"),
                duration_minutes=validated_data.get("duration_minutes"),
                price_cents=validated_data.get("price_cents"),
                currency=validated_data.get("currency"),
                is_active=validated_data.get("is_active"),
            )
        except DjangoValidationError as exc:
            _raise_drf_validation_error(exc)

        response_serializer = CatalogServiceResponseSerializer(
            catalog_service_to_dict(service=service)
        )
        return api_response(request, data=response_serializer.data, status=status.HTTP_200_OK)

    @extend_schema(summary="删除理发师下的服务项目", responses={204: None})
    def delete(self, request, *args, **kwargs):
        """物理删除指定理发师下未被引用的服务项目。

        Args:
            request: DRF 请求对象。

        Returns:
            Response: HTTP 204 空响应。
        """
        stylist = self._get_stylist()
        service = self._get_service(stylist=stylist)
        try:
            catalog_service_delete(service=service)
        except DjangoValidationError as exc:
            _raise_drf_validation_error(exc)
        return Response(status=status.HTTP_204_NO_CONTENT)
