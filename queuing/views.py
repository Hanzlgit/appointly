from accounts.permissions import RequiresStaff
from appointly.api.envelope import api_response
from appointly.api.openapi import enveloped_response_serializer
from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from catalog.models import Stylist
from catalog.services.stylist import catalog_stylist_update
from queuing.presenters import queue_ticket_to_dict
from queuing.selectors import queue_ticket_get, queue_ticket_list_for_stylist, queue_ticket_mine
from queuing.serializers import (
    ConsoleQueueTicketActionRequestSerializer,
    QueueListQuerySerializer,
    QueueTicketCancelRequestSerializer,
    QueueTicketCreateRequestSerializer,
    QueueTicketListResponseSerializer,
    QueueTicketResponseSerializer,
    StylistQueueStatusUpdateRequestSerializer,
)
from queuing.services.ticket_create import queue_ticket_create
from queuing.services.ticket_transition import (
    queue_ticket_call,
    queue_ticket_cancel,
    queue_ticket_complete,
    queue_ticket_move_to_tail,
    queue_ticket_start,
)


def _raise_validation_error(exc: DjangoValidationError) -> None:
    """将 Django ValidationError 转为 DRF ValidationError。

    Args:
        exc (DjangoValidationError): Django 校验异常。

    Raises:
        ValidationError: DRF 校验异常。
    """
    if hasattr(exc, "message_dict"):
        raise ValidationError(exc.message_dict) from exc
    if hasattr(exc, "messages"):
        raise ValidationError(exc.messages) from exc
    raise ValidationError(str(exc)) from exc


class QueueTicketListCreateView(APIView):
    """顾客取号与查询当前排队。"""

    def get_permissions(self):
        """GET 与 POST 均需登录。"""
        return [IsAuthenticated()]

    @extend_schema(
        summary="我的当前排队",
        responses={200: enveloped_response_serializer(QueueTicketResponseSerializer)},
    )
    def get(self, request, *args, **kwargs):
        """返回当前有效排队号。

        Args:
            request: DRF 请求对象。

        Returns:
            Response: 排队详情或 null。
        """
        ticket = queue_ticket_mine(customer=request.user)
        if ticket is None:
            return api_response(request, data=None)
        response_serializer = QueueTicketResponseSerializer(queue_ticket_to_dict(ticket=ticket))
        return api_response(request, data=response_serializer.data)

    @extend_schema(
        summary="取号排队",
        request=QueueTicketCreateRequestSerializer,
        responses={201: enveloped_response_serializer(QueueTicketResponseSerializer)},
    )
    def post(self, request, *args, **kwargs):
        """创建排队号。

        Args:
            request: DRF 请求对象。

        Returns:
            Response: 新建排队号。
        """
        request_serializer = QueueTicketCreateRequestSerializer(data=request.data)
        request_serializer.is_valid(raise_exception=True)
        validated_data = request_serializer.validated_data
        try:
            ticket = queue_ticket_create(
                customer=request.user,
                stylist_id=validated_data["stylist_id"],
                service_id=validated_data["service_id"],
                idempotency_key=validated_data["idempotency_key"],
            )
        except DjangoValidationError as exc:
            _raise_validation_error(exc)
        ticket = queue_ticket_get(ticket_id=ticket.id)
        response_serializer = QueueTicketResponseSerializer(queue_ticket_to_dict(ticket=ticket))
        return api_response(request, data=response_serializer.data, status=status.HTTP_201_CREATED)


class QueueTicketRetrieveView(APIView):
    """排队详情。"""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="排队详情",
        responses={200: enveloped_response_serializer(QueueTicketResponseSerializer)},
    )
    def get(self, request, ticket_id: int, *args, **kwargs):
        """查询指定排队号详情。

        Args:
            request: DRF 请求对象。
            ticket_id (int): 排队号 ID。

        Returns:
            Response: 排队详情。
        """
        ticket = queue_ticket_get(ticket_id=ticket_id)
        if ticket is None or ticket.customer_id != request.user.id:
            raise NotFound("排队号不存在。")
        response_serializer = QueueTicketResponseSerializer(queue_ticket_to_dict(ticket=ticket))
        return api_response(request, data=response_serializer.data)


class QueueTicketCancelView(APIView):
    """顾客取消排队。"""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="取消排队",
        request=QueueTicketCancelRequestSerializer,
        responses={200: enveloped_response_serializer(QueueTicketResponseSerializer)},
    )
    def post(self, request, ticket_id: int, *args, **kwargs):
        """顾客取消 waiting 排队号。

        Args:
            request: DRF 请求对象。
            ticket_id (int): 排队号 ID。

        Returns:
            Response: 取消后的排队号。
        """
        ticket = queue_ticket_get(ticket_id=ticket_id)
        if ticket is None or ticket.customer_id != request.user.id:
            raise NotFound("排队号不存在。")
        request_serializer = QueueTicketCancelRequestSerializer(data=request.data)
        request_serializer.is_valid(raise_exception=True)
        try:
            updated = queue_ticket_cancel(
                ticket_id=ticket_id,
                cancel_reason=request_serializer.validated_data.get("reason", ""),
                by_customer=True,
            )
        except DjangoValidationError as exc:
            _raise_validation_error(exc)
        updated = queue_ticket_get(ticket_id=updated.id)
        response_serializer = QueueTicketResponseSerializer(queue_ticket_to_dict(ticket=updated))
        return api_response(request, data=response_serializer.data)


class ConsoleQueueTicketCallView(APIView):
    """管理台叫号。"""

    permission_classes = [RequiresStaff]

    @extend_schema(
        summary="叫号",
        responses={200: enveloped_response_serializer(QueueTicketResponseSerializer)},
    )
    def post(self, request, ticket_id: int, *args, **kwargs):
        """叫号指定排队号。

        Args:
            request: DRF 请求对象。
            ticket_id (int): 排队号 ID。

        Returns:
            Response: 叫号后的排队号。
        """
        try:
            ticket = queue_ticket_call(ticket_id=ticket_id)
        except DjangoValidationError as exc:
            _raise_validation_error(exc)
        ticket = queue_ticket_get(ticket_id=ticket.id)
        response_serializer = QueueTicketResponseSerializer(queue_ticket_to_dict(ticket=ticket))
        return api_response(request, data=response_serializer.data)


class ConsoleQueueTicketStartView(APIView):
    """管理台开始服务。"""

    permission_classes = [RequiresStaff]

    @extend_schema(
        summary="开始服务",
        responses={200: enveloped_response_serializer(QueueTicketResponseSerializer)},
    )
    def post(self, request, ticket_id: int, *args, **kwargs):
        """确认顾客到场并开始服务。

        Args:
            request: DRF 请求对象。
            ticket_id (int): 排队号 ID。

        Returns:
            Response: 更新后的排队号。
        """
        try:
            ticket = queue_ticket_start(ticket_id=ticket_id)
        except DjangoValidationError as exc:
            _raise_validation_error(exc)
        ticket = queue_ticket_get(ticket_id=ticket.id)
        response_serializer = QueueTicketResponseSerializer(queue_ticket_to_dict(ticket=ticket))
        return api_response(request, data=response_serializer.data)


class ConsoleQueueTicketCompleteView(APIView):
    """管理台完成服务。"""

    permission_classes = [RequiresStaff]

    @extend_schema(
        summary="完成服务",
        responses={200: enveloped_response_serializer(QueueTicketResponseSerializer)},
    )
    def post(self, request, ticket_id: int, *args, **kwargs):
        """标记服务完成。

        Args:
            request: DRF 请求对象。
            ticket_id (int): 排队号 ID。

        Returns:
            Response: 更新后的排队号。
        """
        try:
            ticket = queue_ticket_complete(ticket_id=ticket_id)
        except DjangoValidationError as exc:
            _raise_validation_error(exc)
        ticket = queue_ticket_get(ticket_id=ticket.id)
        response_serializer = QueueTicketResponseSerializer(queue_ticket_to_dict(ticket=ticket))
        return api_response(request, data=response_serializer.data)


class ConsoleQueueTicketCancelView(APIView):
    """管理台取消排队。"""

    permission_classes = [RequiresStaff]

    @extend_schema(
        summary="取消排队",
        request=ConsoleQueueTicketActionRequestSerializer,
        responses={200: enveloped_response_serializer(QueueTicketResponseSerializer)},
    )
    def post(self, request, ticket_id: int, *args, **kwargs):
        """管理员取消排队号。

        Args:
            request: DRF 请求对象。
            ticket_id (int): 排队号 ID。

        Returns:
            Response: 更新后的排队号。
        """
        request_serializer = ConsoleQueueTicketActionRequestSerializer(data=request.data)
        request_serializer.is_valid(raise_exception=True)
        try:
            ticket = queue_ticket_cancel(
                ticket_id=ticket_id,
                cancel_reason=request_serializer.validated_data.get("reason", ""),
                by_customer=False,
            )
        except DjangoValidationError as exc:
            _raise_validation_error(exc)
        ticket = queue_ticket_get(ticket_id=ticket.id)
        response_serializer = QueueTicketResponseSerializer(queue_ticket_to_dict(ticket=ticket))
        return api_response(request, data=response_serializer.data)


class ConsoleQueueTicketMoveToTailView(APIView):
    """管理台移到队尾。"""

    permission_classes = [RequiresStaff]

    @extend_schema(
        summary="移到队尾",
        responses={200: enveloped_response_serializer(QueueTicketResponseSerializer)},
    )
    def post(self, request, ticket_id: int, *args, **kwargs):
        """将已叫号顾客移到队尾。

        Args:
            request: DRF 请求对象。
            ticket_id (int): 排队号 ID。

        Returns:
            Response: 更新后的排队号。
        """
        try:
            ticket = queue_ticket_move_to_tail(ticket_id=ticket_id)
        except DjangoValidationError as exc:
            _raise_validation_error(exc)
        ticket = queue_ticket_get(ticket_id=ticket.id)
        response_serializer = QueueTicketResponseSerializer(queue_ticket_to_dict(ticket=ticket))
        return api_response(request, data=response_serializer.data)


class ConsoleStylistQueueListView(APIView):
    """管理台查看理发师当日队列。"""

    permission_classes = [RequiresStaff]

    @extend_schema(
        summary="理发师当日队列",
        parameters=[QueueListQuerySerializer],
        responses={200: enveloped_response_serializer(QueueTicketListResponseSerializer)},
    )
    def get(self, request, stylist_id: int, *args, **kwargs):
        """分页返回理发师今日排队列表。

        Args:
            request: DRF 请求对象。
            stylist_id (int): 理发师 ID。

        Returns:
            Response: 队列分页列表。
        """
        query_serializer = QueueListQuerySerializer(data=request.query_params)
        query_serializer.is_valid(raise_exception=True)
        validated = query_serializer.validated_data
        queryset = queue_ticket_list_for_stylist(
            stylist_id=stylist_id,
            queue_date=timezone.localdate(),
            status=validated["status"] or None,
            search=validated["q"],
        )
        total = queryset.count()
        page = validated["page"]
        page_size = validated["page_size"]
        offset = (page - 1) * page_size
        items = list(queryset[offset : offset + page_size])
        response_serializer = QueueTicketListResponseSerializer(
            {
                "items": [queue_ticket_to_dict(ticket=ticket) for ticket in items],
                "total": total,
                "page": page,
                "page_size": page_size,
            }
        )
        return api_response(request, data=response_serializer.data)


class ConsoleStylistQueueStatusUpdateView(APIView):
    """管理台更新理发师接单状态。"""

    permission_classes = [RequiresStaff]

    @extend_schema(
        summary="更新理发师接单状态",
        request=StylistQueueStatusUpdateRequestSerializer,
    )
    def patch(self, request, stylist_id: int, *args, **kwargs):
        """更新 queue_status。

        Args:
            request: DRF 请求对象。
            stylist_id (int): 理发师 ID。

        Returns:
            Response: 空 data 成功响应。
        """
        request_serializer = StylistQueueStatusUpdateRequestSerializer(data=request.data)
        request_serializer.is_valid(raise_exception=True)
        try:
            stylist = Stylist.objects.get(pk=stylist_id)
        except Stylist.DoesNotExist as exc:
            raise NotFound("理发师不存在。") from exc
        try:
            catalog_stylist_update(
                stylist=stylist,
                queue_status=request_serializer.validated_data["queue_status"],
            )
        except DjangoValidationError as exc:
            _raise_validation_error(exc)
        return api_response(request, data=None)
