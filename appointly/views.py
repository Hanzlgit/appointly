from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.views import APIView

from appointly.api.envelope import api_response
from appointly.api.openapi import ApiEnvelopeWithNullDataSerializer


class PingView(APIView):
    authentication_classes = []
    permission_classes = []

    @extend_schema(
        summary="API 存活探测",
        responses={200: ApiEnvelopeWithNullDataSerializer},
    )
    def get(self, request, *args, **kwargs):
        """返回 API 存活状态。

        Args:
            request: DRF 请求对象。

        Returns:
            Response: 含 ``status: ok`` 的标准 envelope 响应。
        """
        return api_response(request, data={"status": "ok"}, status=status.HTTP_200_OK)
