from appointly.api.envelope import api_response
from appointly.api.openapi import enveloped_response_serializer
from drf_spectacular.utils import extend_schema
from rest_framework.views import APIView
from tenants.permissions import RequiresTenantStaffOrAdmin
from tenants.selectors import tenant_membership_role_get_for_user
from tenants.views import TenantContextMixin

from audit.selectors import audit_log_list_for_tenant, audit_log_to_dict
from audit.serializers import AuditLogListResponseSerializer, AuditLogResponseSerializer


class AuditLogListView(TenantContextMixin, APIView):
    permission_classes = [RequiresTenantStaffOrAdmin]

    @extend_schema(
        summary="列出租户审计日志",
        responses={200: enveloped_response_serializer(AuditLogListResponseSerializer)},
    )
    def get(self, request, *args, **kwargs):
        """返回租户下审计日志只读列表。

        Args:
            request: DRF 请求对象。

        Returns:
            Response: 含 ``logs`` 的标准 envelope 响应。
        """
        tenant = self.get_tenant()
        role = tenant_membership_role_get_for_user(tenant=tenant, user=request.user)
        action = request.query_params.get("action")
        target_type = request.query_params.get("target_type")
        logs = audit_log_list_for_tenant(
            tenant=tenant,
            action=action,
            target_type=target_type,
        )
        response_serializer = AuditLogListResponseSerializer(
            {
                "logs": [
                    AuditLogResponseSerializer(
                        audit_log_to_dict(log=log, viewer_role=role),
                    ).data
                    for log in logs
                ],
            }
        )
        return api_response(request, data=response_serializer.data)
