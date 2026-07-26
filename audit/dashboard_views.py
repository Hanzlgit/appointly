from appointly.api.envelope import api_response
from appointly.api.openapi import enveloped_response_serializer
from drf_spectacular.utils import extend_schema
from rest_framework.views import APIView
from tenants.permissions import RequiresTenantAdmin
from tenants.views import TenantContextMixin

from audit.dashboard_serializers import DashboardSummaryResponseSerializer
from audit.services.dashboard import dashboard_summary_get


class DashboardSummaryView(TenantContextMixin, APIView):
    permission_classes = [RequiresTenantAdmin]

    @extend_schema(
        summary="获取租户经营看板汇总",
        responses={200: enveloped_response_serializer(DashboardSummaryResponseSerializer)},
    )
    def get(self, request, *args, **kwargs):
        """返回今日汇总、趋势、地点分布、资源占用与热门服务。

        Args:
            request: DRF 请求对象。

        Returns:
            Response: 看板汇总 envelope 响应。
        """
        tenant = self.get_tenant()
        reference_date = request.query_params.get("date")
        location_id = request.query_params.get("location_id")
        parsed_location_id = int(location_id) if location_id else None
        summary = dashboard_summary_get(
            tenant=tenant,
            reference_date=reference_date,
            location_id=parsed_location_id,
        )
        response_serializer = DashboardSummaryResponseSerializer(summary)
        return api_response(request, data=response_serializer.data)
