from appointly.api.envelope import api_response
from appointly.api.openapi import enveloped_response_serializer
from drf_spectacular.utils import extend_schema
from rest_framework.views import APIView
from tenants.permissions import RequiresTenantCustomer
from tenants.views import TenantContextMixin

from notifications.selectors import notification_list_for_user
from notifications.serializers import NotificationListItemResponseSerializer


class NotificationListView(TenantContextMixin, APIView):
    permission_classes = [RequiresTenantCustomer]

    @extend_schema(
        summary="列出当前用户的站内通知",
        responses={200: enveloped_response_serializer(NotificationListItemResponseSerializer)},
    )
    def get(self, request, *args, **kwargs):
        """返回当前客户在租户下的站内通知列表。

        Args:
            request: DRF 请求对象。

        Returns:
            Response: 通知列表 envelope 响应。
        """
        tenant = self.get_tenant()
        notifications = notification_list_for_user(tenant=tenant, user=request.user)
        response_serializer = NotificationListItemResponseSerializer(notifications, many=True)
        return api_response(request, data=response_serializer.data)
