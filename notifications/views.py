from appointly.api.envelope import api_response
from appointly.api.openapi import enveloped_response_serializer
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.exceptions import NotFound
from rest_framework.views import APIView
from tenants.permissions import RequiresTenantCustomer
from tenants.views import TenantContextMixin

from notifications.models import Notification
from notifications.selectors import notification_list_for_user
from notifications.serializers import (
    NotificationListItemResponseSerializer,
    NotificationListQuerySerializer,
    NotificationListResponseSerializer,
    NotificationReadAllResponseSerializer,
)
from notifications.services.notification import (
    notification_mark_all_read,
    notification_mark_read,
)


def _notification_to_dict(notification) -> dict:
    """将通知模型转为 API 字典。

    Args:
        notification: Notification 实例。

    Returns:
        dict: 序列化用字典。
    """
    return {
        "id": notification.id,
        "notification_type": notification.notification_type,
        "title": notification.title,
        "body": notification.body,
        "booking_id": notification.booking_id,
        "read_at": notification.read_at,
        "created_at": notification.created_at,
    }


class NotificationListView(TenantContextMixin, APIView):
    permission_classes = [RequiresTenantCustomer]

    @extend_schema(
        summary="列出当前用户的站内通知",
        parameters=[NotificationListQuerySerializer],
        responses={200: enveloped_response_serializer(NotificationListResponseSerializer)},
    )
    def get(self, request, *args, **kwargs):
        """返回当前客户在租户下的分页站内通知列表。

        Args:
            request: DRF 请求对象。

        Returns:
            Response: 分页通知列表 envelope 响应。
        """
        tenant = self.get_tenant()
        query_serializer = NotificationListQuerySerializer(data=request.query_params)
        query_serializer.is_valid(raise_exception=True)
        validated = query_serializer.validated_data

        result = notification_list_for_user(
            tenant=tenant,
            user=request.user,
            page=validated["page"],
            page_size=validated["page_size"],
            q=validated["q"],
            unread_only=validated["unread_only"],
            notification_type=validated["type"],
        )
        response_serializer = NotificationListResponseSerializer(
            {
                "items": [_notification_to_dict(item) for item in result.items],
                "total": result.total,
                "page": validated["page"],
                "page_size": validated["page_size"],
                "unread_count": result.unread_count,
            }
        )
        return api_response(request, data=response_serializer.data)


class NotificationMarkReadView(TenantContextMixin, APIView):
    permission_classes = [RequiresTenantCustomer]

    @extend_schema(
        summary="将单条通知标记为已读",
        responses={200: enveloped_response_serializer(NotificationListItemResponseSerializer)},
    )
    def patch(self, request, notification_id: int, *args, **kwargs):
        """将指定通知标记为已读。

        Args:
            request: DRF 请求对象。
            notification_id (int): 通知 ID。

        Returns:
            Response: 更新后的通知 envelope 响应。
        """
        tenant = self.get_tenant()
        try:
            notification = notification_mark_read(
                tenant=tenant,
                user=request.user,
                notification_id=notification_id,
            )
        except Notification.DoesNotExist as exc:
            raise NotFound("通知不存在。") from exc

        response_serializer = NotificationListItemResponseSerializer(
            _notification_to_dict(notification)
        )
        return api_response(request, data=response_serializer.data)


class NotificationReadAllView(TenantContextMixin, APIView):
    permission_classes = [RequiresTenantCustomer]

    @extend_schema(
        summary="将全部通知标记为已读",
        responses={200: enveloped_response_serializer(NotificationReadAllResponseSerializer)},
    )
    def post(self, request, *args, **kwargs):
        """将当前用户在租户下的全部未读通知标记为已读。

        Args:
            request: DRF 请求对象。

        Returns:
            Response: 含标记数量的 envelope 响应。
        """
        tenant = self.get_tenant()
        marked_count = notification_mark_all_read(tenant=tenant, user=request.user)
        response_serializer = NotificationReadAllResponseSerializer(
            {"marked_count": marked_count}
        )
        return api_response(request, data=response_serializer.data, status=status.HTTP_200_OK)
