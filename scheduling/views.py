from appointly.api.envelope import api_response
from appointly.api.openapi import enveloped_response_serializer
from audit.constants import AuditAction
from audit.services.audit_log import audit_log_booking_status_change, audit_log_record
from audit.services.http_context import audit_http_context
from catalog.models import Location, Resource
from django.core.exceptions import ValidationError as DjangoValidationError
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.exceptions import NotFound
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.response import Response
from rest_framework.views import APIView
from tenants.models import TenantRole
from tenants.permissions import (
    RequiresTenantAdmin,
    RequiresTenantCustomer,
    RequiresTenantMembership,
    RequiresTenantStaffOrAdmin,
)
from tenants.selectors import tenant_customer_get_for_user, tenant_membership_role_get_for_user
from tenants.views import TenantContextMixin

from scheduling.models import Booking, BookingCancelActor, ScheduleRule, TimeSlot
from scheduling.selectors import (
    scheduling_booking_list_for_customer,
    scheduling_booking_list_for_staff,
    scheduling_booking_settings_to_dict,
    scheduling_booking_to_dict,
    scheduling_schedule_rule_get_for_tenant,
    scheduling_schedule_rule_list_for_tenant,
    scheduling_schedule_rule_to_dict,
    scheduling_time_slot_get_for_tenant,
    scheduling_time_slot_to_dict,
)
from scheduling.serializers import (
    AvailabilityAggregateQueryResponseSerializer,
    AvailabilityQueryRequestSerializer,
    AvailabilityResourceQueryResponseSerializer,
    BookingCancelRequestSerializer,
    BookingContactUpdateRequestSerializer,
    BookingCreateRequestSerializer,
    BookingListResponseSerializer,
    BookingPartySizeUpdateRequestSerializer,
    BookingRescheduleRequestSerializer,
    BookingResponseSerializer,
    ScheduleRuleCreateRequestSerializer,
    ScheduleRuleListQuerySerializer,
    ScheduleRuleListResponseSerializer,
    ScheduleRuleResponseSerializer,
    ScheduleRuleUpdateRequestSerializer,
    StaffBookingCreateRequestSerializer,
    StaffBookingListResponseSerializer,
    StaffBookingResponseSerializer,
    TenantBookingSettingsResponseSerializer,
    TenantBookingSettingsUpdateRequestSerializer,
    TimeSlotBatchCloseConflictResponseSerializer,
    TimeSlotBatchCloseRequestSerializer,
    TimeSlotBatchCloseResponseSerializer,
    TimeSlotCapacityAdjustRequestSerializer,
    TimeSlotCreateRequestSerializer,
    TimeSlotResponseSerializer,
)
from scheduling.services.availability_cache import scheduling_availability_query_cached
from scheduling.services.booking_create import scheduling_booking_create
from scheduling.services.booking_settings import (
    scheduling_booking_settings_get_for_tenant,
    scheduling_booking_settings_update,
)
from scheduling.services.booking_staff_create import scheduling_booking_staff_create
from scheduling.services.booking_transition import (
    scheduling_booking_cancel,
    scheduling_booking_complete,
    scheduling_booking_confirm,
    scheduling_booking_contact_update,
    scheduling_booking_get_for_tenant,
    scheduling_booking_no_show,
    scheduling_booking_party_size_update,
    scheduling_booking_reject,
    scheduling_booking_reschedule,
)
from scheduling.services.capacity_adjust import scheduling_timeslot_capacity_adjust
from scheduling.services.schedule_rule import (
    scheduling_schedule_rule_create,
    scheduling_schedule_rule_update,
    scheduling_timeslots_batch_close,
)
from scheduling.services.time_slot import (
    scheduling_timeslot_close,
    scheduling_timeslot_create,
    scheduling_timeslots_generate_for_rule,
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


def _validation_error_response(request, exc: DjangoValidationError) -> Response:
    """将带冲突列表的 ValidationError 转为 envelope 响应。

    Args:
        request: DRF 请求对象。
        exc (DjangoValidationError): Django 校验异常。

    Returns:
        Response: 含冲突详情或普通校验错误的 envelope 响应。
    """
    conflicts = None
    if getattr(exc, "params", None) and isinstance(exc.params, dict):
        conflicts = exc.params.get("conflicts")
    if conflicts is not None:
        response_serializer = TimeSlotBatchCloseConflictResponseSerializer({"conflicts": conflicts})
        return api_response(
            request,
            data=response_serializer.data,
            message=str(exc.message),
            code=1,
            status=status.HTTP_400_BAD_REQUEST,
        )
    _raise_drf_validation_error(exc)
    return Response(status=status.HTTP_400_BAD_REQUEST)


def _scheduling_customer_booking_get(
    *,
    tenant,
    customer,
    booking_id: int,
) -> Booking:
    """获取客户拥有的预约，非本人返回 404。

    Args:
        tenant: 目标租户。
        customer: 客户档案。
        booking_id (int): 预约 ID。

    Returns:
        Booking: 匹配的预约。

    Raises:
        NotFound: 预约不存在或非本人。
    """
    try:
        booking = scheduling_booking_get_for_tenant(tenant=tenant, booking_id=booking_id)
    except Booking.DoesNotExist as exc:
        raise NotFound("预约不存在。") from exc
    if booking.customer_id != customer.id:
        raise NotFound("预约不存在。")
    return booking


class ScheduleRuleListCreateView(TenantContextMixin, APIView):
    permission_classes = [RequiresTenantMembership, RequiresTenantAdmin]

    @extend_schema(
        summary="列出周期排班规则",
        parameters=[ScheduleRuleListQuerySerializer],
        responses={200: enveloped_response_serializer(ScheduleRuleListResponseSerializer)},
    )
    def get(self, request, *args, **kwargs):
        """列出租户下的周期排班规则，可按资源过滤。

        Args:
            request: DRF 请求对象。

        Returns:
            Response: 含 ``rules`` 列表的标准 envelope 响应。
        """
        tenant = self.get_tenant()
        query_serializer = ScheduleRuleListQuerySerializer(data=request.query_params)
        query_serializer.is_valid(raise_exception=True)
        query_data = query_serializer.validated_data

        rules = scheduling_schedule_rule_list_for_tenant(
            tenant=tenant,
            resource_id=query_data.get("resource_id"),
        )
        response_serializer = ScheduleRuleListResponseSerializer(
            {
                "rules": [
                    ScheduleRuleResponseSerializer(scheduling_schedule_rule_to_dict(rule=rule)).data
                    for rule in rules
                ],
            }
        )
        return api_response(request, data=response_serializer.data, status=status.HTTP_200_OK)

    @extend_schema(
        summary="创建周期排班规则",
        request=ScheduleRuleCreateRequestSerializer,
        responses={201: enveloped_response_serializer(ScheduleRuleResponseSerializer)},
    )
    def post(self, request, *args, **kwargs):
        """创建周期排班规则。

        Args:
            request: DRF 请求对象。

        Returns:
            Response: 含新规则的标准 envelope 响应，HTTP 201。
        """
        tenant = self.get_tenant()
        request_serializer = ScheduleRuleCreateRequestSerializer(data=request.data)
        request_serializer.is_valid(raise_exception=True)
        validated_data = request_serializer.validated_data

        try:
            rule = scheduling_schedule_rule_create(
                tenant=tenant,
                location_id=validated_data["location_id"],
                resource_id=validated_data["resource_id"],
                days_of_week=validated_data["days_of_week"],
                start_time=validated_data["start_time"],
                end_time=validated_data["end_time"],
                slot_interval_minutes=validated_data["slot_interval_minutes"],
                capacity=validated_data["capacity"],
            )
        except DjangoValidationError as exc:
            _raise_drf_validation_error(exc)

        scheduling_timeslots_generate_for_rule(tenant=tenant, rule=rule)

        response_serializer = ScheduleRuleResponseSerializer(
            scheduling_schedule_rule_to_dict(rule=rule)
        )
        return api_response(
            request,
            data=response_serializer.data,
            message="created",
            status=status.HTTP_201_CREATED,
        )


class ScheduleRuleUpdateView(TenantContextMixin, APIView):
    permission_classes = [RequiresTenantMembership, RequiresTenantAdmin]

    def _get_rule(self) -> ScheduleRule:
        """从 URL 解析并返回当前租户下的排班规则。

        Returns:
            ScheduleRule: 匹配的排班规则。

        Raises:
            NotFound: 规则不存在。
        """
        tenant = self.get_tenant()
        rule_id = self.kwargs["rule_id"]
        try:
            return scheduling_schedule_rule_get_for_tenant(tenant=tenant, rule_id=rule_id)
        except ScheduleRule.DoesNotExist as exc:
            raise NotFound("排班规则不存在。") from exc

    @extend_schema(
        summary="变更周期排班规则",
        request=ScheduleRuleUpdateRequestSerializer,
        responses={200: enveloped_response_serializer(ScheduleRuleResponseSerializer)},
    )
    def patch(self, request, *args, **kwargs):
        """变更排班规则并在生效日重新生成时段。

        Args:
            request: DRF 请求对象。

        Returns:
            Response: 含更新后规则的标准 envelope 响应。
        """
        tenant = self.get_tenant()
        rule = self._get_rule()
        request_serializer = ScheduleRuleUpdateRequestSerializer(data=request.data, partial=True)
        request_serializer.is_valid(raise_exception=True)
        validated_data = request_serializer.validated_data

        before_value = {
            "capacity": rule.capacity,
            "is_active": rule.is_active,
        }
        try:
            rule = scheduling_schedule_rule_update(
                tenant=tenant,
                rule=rule,
                effective_date=validated_data["effective_date"],
                location_id=validated_data.get("location_id"),
                resource_id=validated_data.get("resource_id"),
                days_of_week=validated_data.get("days_of_week"),
                start_time=validated_data.get("start_time"),
                end_time=validated_data.get("end_time"),
                slot_interval_minutes=validated_data.get("slot_interval_minutes"),
                capacity=validated_data.get("capacity"),
                is_active=validated_data.get("is_active"),
            )
        except DjangoValidationError as exc:
            _raise_drf_validation_error(exc)

        http_context = audit_http_context(request=request)
        audit_log_record(
            tenant=tenant,
            operator=http_context["operator"],
            request_id=http_context["request_id"],
            ip_address=http_context["ip_address"],
            action=AuditAction.SCHEDULE_CHANGE,
            target_type="schedule_rule",
            target_id=rule.id,
            before_value=before_value,
            after_value={
                "capacity": rule.capacity,
                "is_active": rule.is_active,
            },
            details={"effective_date": str(validated_data["effective_date"])},
        )

        response_serializer = ScheduleRuleResponseSerializer(
            scheduling_schedule_rule_to_dict(rule=rule)
        )
        return api_response(request, data=response_serializer.data, status=status.HTTP_200_OK)


class TimeSlotCreateView(TenantContextMixin, APIView):
    permission_classes = [RequiresTenantMembership, RequiresTenantAdmin]

    @extend_schema(
        summary="手工创建固定时段",
        request=TimeSlotCreateRequestSerializer,
        responses={201: enveloped_response_serializer(TimeSlotResponseSerializer)},
    )
    def post(self, request, *args, **kwargs):
        """手工补充单个固定时段。

        Args:
            request: DRF 请求对象。

        Returns:
            Response: 含新时段的标准 envelope 响应，HTTP 201。
        """
        tenant = self.get_tenant()
        request_serializer = TimeSlotCreateRequestSerializer(data=request.data)
        request_serializer.is_valid(raise_exception=True)
        validated_data = request_serializer.validated_data

        try:
            location = Location.objects.get(id=validated_data["location_id"], tenant=tenant)
            resource = Resource.objects.get(id=validated_data["resource_id"], tenant=tenant)
            time_slot = scheduling_timeslot_create(
                tenant=tenant,
                location=location,
                resource=resource,
                start=validated_data["start"],
                end=validated_data["end"],
                capacity=validated_data["capacity"],
            )
        except Location.DoesNotExist as exc:
            raise NotFound("服务地点不存在。") from exc
        except Resource.DoesNotExist as exc:
            raise NotFound("可预约资源不存在。") from exc
        except DjangoValidationError as exc:
            _raise_drf_validation_error(exc)

        response_serializer = TimeSlotResponseSerializer(
            scheduling_time_slot_to_dict(time_slot=time_slot)
        )
        return api_response(
            request,
            data=response_serializer.data,
            message="created",
            status=status.HTTP_201_CREATED,
        )


class TimeSlotCloseView(TenantContextMixin, APIView):
    permission_classes = [RequiresTenantMembership, RequiresTenantAdmin]

    def _get_time_slot(self) -> TimeSlot:
        """从 URL 解析并返回当前租户下的固定时段。

        Returns:
            TimeSlot: 匹配的固定时段。

        Raises:
            NotFound: 时段不存在。
        """
        tenant = self.get_tenant()
        time_slot_id = self.kwargs["time_slot_id"]
        try:
            return scheduling_time_slot_get_for_tenant(tenant=tenant, time_slot_id=time_slot_id)
        except TimeSlot.DoesNotExist as exc:
            raise NotFound("固定时段不存在。") from exc

    @extend_schema(
        summary="关闭单个空闲时段",
        responses={200: enveloped_response_serializer(TimeSlotResponseSerializer)},
    )
    def post(self, request, *args, **kwargs):
        """关闭单个空闲固定时段。

        Args:
            request: DRF 请求对象。

        Returns:
            Response: 含关闭后时段的标准 envelope 响应。
        """
        tenant = self.get_tenant()
        time_slot = self._get_time_slot()

        try:
            time_slot = scheduling_timeslot_close(tenant=tenant, time_slot=time_slot)
        except DjangoValidationError as exc:
            _raise_drf_validation_error(exc)

        response_serializer = TimeSlotResponseSerializer(
            scheduling_time_slot_to_dict(time_slot=time_slot)
        )
        return api_response(request, data=response_serializer.data, status=status.HTTP_200_OK)


class TimeSlotBatchCloseView(TenantContextMixin, APIView):
    permission_classes = [RequiresTenantMembership, RequiresTenantAdmin]

    @extend_schema(
        summary="批量关闭固定时段",
        request=TimeSlotBatchCloseRequestSerializer,
        responses={
            200: enveloped_response_serializer(TimeSlotBatchCloseResponseSerializer),
            400: enveloped_response_serializer(TimeSlotBatchCloseConflictResponseSerializer),
        },
    )
    def post(self, request, *args, **kwargs):
        """按时间范围批量关闭空闲时段。

        Args:
            request: DRF 请求对象。

        Returns:
            Response: 含关闭数量的标准 envelope 响应；冲突时 HTTP 400。
        """
        tenant = self.get_tenant()
        request_serializer = TimeSlotBatchCloseRequestSerializer(data=request.data)
        request_serializer.is_valid(raise_exception=True)
        validated_data = request_serializer.validated_data

        try:
            closed_count = scheduling_timeslots_batch_close(
                tenant=tenant,
                start=validated_data["start"],
                end=validated_data["end"],
                location_id=validated_data.get("location_id"),
                resource_id=validated_data.get("resource_id"),
            )
        except DjangoValidationError as exc:
            return _validation_error_response(request, exc)

        response_serializer = TimeSlotBatchCloseResponseSerializer({"closed_count": closed_count})
        return api_response(request, data=response_serializer.data, status=status.HTTP_200_OK)


class AvailabilityQueryView(TenantContextMixin, APIView):
    authentication_classes = []
    permission_classes = []

    @extend_schema(
        summary="查询可用时段",
        parameters=[AvailabilityQueryRequestSerializer],
        responses={
            200: enveloped_response_serializer(AvailabilityResourceQueryResponseSerializer),
        },
    )
    def get(self, request, *args, **kwargs):
        """查询指定资源或聚合可用容量。

        Args:
            request: DRF 请求对象。

        Returns:
            Response: 含可用时段或聚合容量的标准 envelope 响应。
        """
        tenant = self.get_tenant()
        request_serializer = AvailabilityQueryRequestSerializer(data=request.query_params)
        request_serializer.is_valid(raise_exception=True)
        validated_data = request_serializer.validated_data

        result = scheduling_availability_query_cached(
            tenant=tenant,
            start=validated_data["start"],
            end=validated_data["end"],
            resource_id=validated_data.get("resource_id"),
            service_id=validated_data.get("service_id"),
            location_id=validated_data.get("location_id"),
        )

        if result["mode"] == "resource":
            response_serializer = AvailabilityResourceQueryResponseSerializer(result)
        else:
            response_serializer = AvailabilityAggregateQueryResponseSerializer(result)
        return api_response(request, data=response_serializer.data, status=status.HTTP_200_OK)


class BookingListCreateView(TenantContextMixin, APIView):
    permission_classes = [RequiresTenantCustomer]

    @extend_schema(
        summary="列出当前客户的预约",
        responses={200: enveloped_response_serializer(BookingListResponseSerializer)},
    )
    def get(self, request, *args, **kwargs):
        """列出客户在当前租户下的预约。

        Args:
            request: DRF 请求对象。

        Returns:
            Response: 含预约列表的标准 envelope 响应。
        """
        tenant = self.get_tenant()
        customer = tenant_customer_get_for_user(tenant=tenant, user=request.user)
        bookings = scheduling_booking_list_for_customer(tenant=tenant, customer=customer)
        response_serializer = BookingListResponseSerializer(
            {
                "bookings": [
                    BookingResponseSerializer(
                        scheduling_booking_to_dict(tenant=tenant, booking=booking)
                    ).data
                    for booking in bookings
                ],
            }
        )
        return api_response(request, data=response_serializer.data, status=status.HTTP_200_OK)

    @extend_schema(
        summary="创建预约",
        request=BookingCreateRequestSerializer,
        responses={201: enveloped_response_serializer(BookingResponseSerializer)},
    )
    def post(self, request, *args, **kwargs):
        """客户创建预约，需携带 Idempotency-Key 请求头。

        Args:
            request: DRF 请求对象。

        Returns:
            Response: 含新预约的标准 envelope 响应，HTTP 201。
        """
        idempotency_key = request.headers.get("Idempotency-Key", "").strip()
        if not idempotency_key:
            raise DRFValidationError({"idempotency_key": "必须提供 Idempotency-Key 请求头。"})

        tenant = self.get_tenant()
        customer = tenant_customer_get_for_user(tenant=tenant, user=request.user)
        request_serializer = BookingCreateRequestSerializer(data=request.data)
        request_serializer.is_valid(raise_exception=True)
        validated_data = request_serializer.validated_data

        try:
            booking = scheduling_booking_create(
                tenant=tenant,
                customer=customer,
                idempotency_key=idempotency_key,
                service_id=validated_data["service_id"],
                party_size=validated_data.get("party_size", 1),
                time_slot_id=validated_data.get("time_slot_id"),
                location_id=validated_data.get("location_id"),
                start=validated_data.get("start"),
                end=validated_data.get("end"),
                resource_id=validated_data.get("resource_id"),
                contact_name=validated_data.get("contact_name", ""),
                contact_phone=validated_data.get("contact_phone", ""),
            )
        except DjangoValidationError as exc:
            _raise_drf_validation_error(exc)

        response_serializer = BookingResponseSerializer(
            scheduling_booking_to_dict(tenant=tenant, booking=booking)
        )
        return api_response(
            request,
            data=response_serializer.data,
            message="created",
            status=status.HTTP_201_CREATED,
        )


class TenantBookingSettingsView(TenantContextMixin, APIView):
    permission_classes = [RequiresTenantMembership, RequiresTenantAdmin]

    @extend_schema(
        summary="读取租户预约业务规则",
        responses={200: enveloped_response_serializer(TenantBookingSettingsResponseSerializer)},
    )
    def get(self, request, *args, **kwargs):
        """读取当前租户的预约业务规则。

        Args:
            request: DRF 请求对象。

        Returns:
            Response: 含规则配置的标准 envelope 响应。
        """
        tenant = self.get_tenant()
        settings = scheduling_booking_settings_get_for_tenant(tenant=tenant)
        response_serializer = TenantBookingSettingsResponseSerializer(
            scheduling_booking_settings_to_dict(settings=settings)
        )
        return api_response(request, data=response_serializer.data, status=status.HTTP_200_OK)

    @extend_schema(
        summary="更新租户预约业务规则",
        request=TenantBookingSettingsUpdateRequestSerializer,
        responses={200: enveloped_response_serializer(TenantBookingSettingsResponseSerializer)},
    )
    def patch(self, request, *args, **kwargs):
        """更新当前租户的预约业务规则。

        Args:
            request: DRF 请求对象。

        Returns:
            Response: 含更新后规则的标准 envelope 响应。
        """
        tenant = self.get_tenant()
        request_serializer = TenantBookingSettingsUpdateRequestSerializer(
            data=request.data,
            partial=True,
        )
        request_serializer.is_valid(raise_exception=True)
        validated_data = request_serializer.validated_data

        try:
            settings = scheduling_booking_settings_update(
                tenant=tenant,
                min_advance_minutes=validated_data.get("min_advance_minutes"),
                max_booking_window_days=validated_data.get("max_booking_window_days"),
                pending_retention_minutes=validated_data.get("pending_retention_minutes"),
                cancel_deadline_minutes=validated_data.get("cancel_deadline_minutes"),
                future_booking_limit=validated_data.get("future_booking_limit"),
                confirmation_mode=validated_data.get("confirmation_mode"),
            )
        except DjangoValidationError as exc:
            _raise_drf_validation_error(exc)

        response_serializer = TenantBookingSettingsResponseSerializer(
            scheduling_booking_settings_to_dict(settings=settings)
        )
        return api_response(request, data=response_serializer.data, status=status.HTTP_200_OK)


class BookingConfirmView(TenantContextMixin, APIView):
    permission_classes = [RequiresTenantMembership, RequiresTenantAdmin]

    @extend_schema(
        summary="确认待处理预约",
        responses={200: enveloped_response_serializer(BookingResponseSerializer)},
    )
    def post(self, request, *args, **kwargs):
        """将待确认预约转为已确认。

        Args:
            request: DRF 请求对象。

        Returns:
            Response: 含更新后预约的标准 envelope 响应。
        """
        tenant = self.get_tenant()
        booking_id = self.kwargs["booking_id"]
        try:
            booking = scheduling_booking_get_for_tenant(tenant=tenant, booking_id=booking_id)
        except Booking.DoesNotExist as exc:
            raise NotFound("预约不存在。") from exc

        try:
            old_status = booking.status
            booking = scheduling_booking_confirm(booking=booking)
        except DjangoValidationError as exc:
            _raise_drf_validation_error(exc)

        audit_log_booking_status_change(
            tenant=tenant,
            booking_id=booking.id,
            old_status=old_status,
            new_status=booking.status,
            request=request,
        )

        response_serializer = BookingResponseSerializer(
            scheduling_booking_to_dict(tenant=tenant, booking=booking)
        )
        return api_response(request, data=response_serializer.data, status=status.HTTP_200_OK)


class BookingRejectView(TenantContextMixin, APIView):
    permission_classes = [RequiresTenantMembership, RequiresTenantAdmin]

    @extend_schema(
        summary="拒绝待处理预约",
        responses={200: enveloped_response_serializer(BookingResponseSerializer)},
    )
    def post(self, request, *args, **kwargs):
        """将待确认预约转为已拒绝并释放容量。

        Args:
            request: DRF 请求对象。

        Returns:
            Response: 含更新后预约的标准 envelope 响应。
        """
        tenant = self.get_tenant()
        booking_id = self.kwargs["booking_id"]
        try:
            booking = scheduling_booking_get_for_tenant(tenant=tenant, booking_id=booking_id)
        except Booking.DoesNotExist as exc:
            raise NotFound("预约不存在。") from exc

        try:
            old_status = booking.status
            booking = scheduling_booking_reject(booking=booking)
        except DjangoValidationError as exc:
            _raise_drf_validation_error(exc)

        audit_log_booking_status_change(
            tenant=tenant,
            booking_id=booking.id,
            old_status=old_status,
            new_status=booking.status,
            request=request,
        )

        response_serializer = BookingResponseSerializer(
            scheduling_booking_to_dict(tenant=tenant, booking=booking)
        )
        return api_response(request, data=response_serializer.data, status=status.HTTP_200_OK)


class BookingCancelView(TenantContextMixin, APIView):
    permission_classes = [RequiresTenantCustomer]

    @extend_schema(
        summary="客户取消预约",
        request=BookingCancelRequestSerializer,
        responses={200: enveloped_response_serializer(BookingResponseSerializer)},
    )
    def post(self, request, *args, **kwargs):
        """客户在最晚取消时间前取消预约。

        Args:
            request: DRF 请求对象。

        Returns:
            Response: 含更新后预约的标准 envelope 响应。
        """
        tenant = self.get_tenant()
        customer = tenant_customer_get_for_user(tenant=tenant, user=request.user)
        booking_id = self.kwargs["booking_id"]
        booking = _scheduling_customer_booking_get(
            tenant=tenant,
            customer=customer,
            booking_id=booking_id,
        )

        request_serializer = BookingCancelRequestSerializer(data=request.data)
        request_serializer.is_valid(raise_exception=True)
        validated_data = request_serializer.validated_data

        try:
            booking = scheduling_booking_cancel(
                booking=booking,
                actor=BookingCancelActor.CUSTOMER,
                reason=validated_data.get("reason", ""),
                operator=request.user,
            )
        except DjangoValidationError as exc:
            _raise_drf_validation_error(exc)

        response_serializer = BookingResponseSerializer(
            scheduling_booking_to_dict(tenant=tenant, booking=booking)
        )
        return api_response(request, data=response_serializer.data, status=status.HTTP_200_OK)


class BookingRescheduleView(TenantContextMixin, APIView):
    permission_classes = [RequiresTenantCustomer]

    @extend_schema(
        summary="客户改期",
        request=BookingRescheduleRequestSerializer,
        responses={200: enveloped_response_serializer(BookingResponseSerializer)},
    )
    def post(self, request, *args, **kwargs):
        """客户将预约改至新时段。

        Args:
            request: DRF 请求对象。

        Returns:
            Response: 含新预约的标准 envelope 响应。
        """
        tenant = self.get_tenant()
        customer = tenant_customer_get_for_user(tenant=tenant, user=request.user)
        booking = _scheduling_customer_booking_get(
            tenant=tenant,
            customer=customer,
            booking_id=self.kwargs["booking_id"],
        )

        request_serializer = BookingRescheduleRequestSerializer(data=request.data)
        request_serializer.is_valid(raise_exception=True)
        validated_data = request_serializer.validated_data

        try:
            new_booking = scheduling_booking_reschedule(
                booking=booking,
                new_time_slot_id=validated_data["time_slot_id"],
                idempotency_key=validated_data["idempotency_key"],
            )
        except DjangoValidationError as exc:
            _raise_drf_validation_error(exc)

        response_serializer = BookingResponseSerializer(
            scheduling_booking_to_dict(tenant=tenant, booking=new_booking)
        )
        return api_response(request, data=response_serializer.data, status=status.HTTP_200_OK)


class BookingPartySizeUpdateView(TenantContextMixin, APIView):
    permission_classes = [RequiresTenantCustomer]

    @extend_schema(
        summary="客户修改预约人数",
        request=BookingPartySizeUpdateRequestSerializer,
        responses={200: enveloped_response_serializer(BookingResponseSerializer)},
    )
    def patch(self, request, *args, **kwargs):
        """客户修改预约人数。

        Args:
            request: DRF 请求对象。

        Returns:
            Response: 含更新后预约的标准 envelope 响应。
        """
        tenant = self.get_tenant()
        customer = tenant_customer_get_for_user(tenant=tenant, user=request.user)
        booking = _scheduling_customer_booking_get(
            tenant=tenant,
            customer=customer,
            booking_id=self.kwargs["booking_id"],
        )

        request_serializer = BookingPartySizeUpdateRequestSerializer(data=request.data)
        request_serializer.is_valid(raise_exception=True)
        validated_data = request_serializer.validated_data

        try:
            booking = scheduling_booking_party_size_update(
                booking=booking,
                party_size=validated_data["party_size"],
            )
        except DjangoValidationError as exc:
            _raise_drf_validation_error(exc)

        response_serializer = BookingResponseSerializer(
            scheduling_booking_to_dict(tenant=tenant, booking=booking)
        )
        return api_response(request, data=response_serializer.data, status=status.HTTP_200_OK)


class BookingContactUpdateView(TenantContextMixin, APIView):
    permission_classes = [RequiresTenantCustomer]

    @extend_schema(
        summary="客户更新预约联系人",
        request=BookingContactUpdateRequestSerializer,
        responses={200: enveloped_response_serializer(BookingResponseSerializer)},
    )
    def patch(self, request, *args, **kwargs):
        """更新代他人预约的联系人；手机号变更需 OTP。

        Args:
            request: DRF 请求对象。

        Returns:
            Response: 含更新后预约的标准 envelope 响应。
        """
        tenant = self.get_tenant()
        customer = tenant_customer_get_for_user(tenant=tenant, user=request.user)
        booking = _scheduling_customer_booking_get(
            tenant=tenant,
            customer=customer,
            booking_id=self.kwargs["booking_id"],
        )

        request_serializer = BookingContactUpdateRequestSerializer(data=request.data)
        request_serializer.is_valid(raise_exception=True)
        validated_data = request_serializer.validated_data

        try:
            booking = scheduling_booking_contact_update(
                booking=booking,
                contact_name=validated_data.get("contact_name", ""),
                contact_phone=validated_data.get("contact_phone", ""),
                otp_code=validated_data.get("otp_code") or None,
            )
        except DjangoValidationError as exc:
            _raise_drf_validation_error(exc)

        response_serializer = BookingResponseSerializer(
            scheduling_booking_to_dict(tenant=tenant, booking=booking)
        )
        return api_response(request, data=response_serializer.data, status=status.HTTP_200_OK)


class StaffBookingListCreateView(TenantContextMixin, APIView):
    permission_classes = [RequiresTenantMembership, RequiresTenantStaffOrAdmin]

    @extend_schema(
        summary="列出后台可见预约",
        responses={200: enveloped_response_serializer(StaffBookingListResponseSerializer)},
    )
    def get(self, request, *args, **kwargs):
        """列出租户全部或工作人员关联资源的预约。

        Args:
            request: DRF 请求对象。

        Returns:
            Response: 含预约列表的标准 envelope 响应。
        """
        tenant = self.get_tenant()
        role = tenant_membership_role_get_for_user(tenant=tenant, user=request.user)
        bookings = scheduling_booking_list_for_staff(
            tenant=tenant,
            user=request.user,
            role=role,
        )
        if role == TenantRole.TENANT_ADMIN and bookings:
            audit_log_record(
                tenant=tenant,
                operator=request.user,
                request_id=getattr(request, "request_id", ""),
                ip_address=request.META.get("REMOTE_ADDR"),
                action=AuditAction.SENSITIVE_VIEW,
                target_type="booking_list",
                target_id=0,
                details={"booking_count": len(bookings)},
            )
        response_serializer = StaffBookingListResponseSerializer(
            {
                "bookings": [
                    StaffBookingResponseSerializer(
                        scheduling_booking_to_dict(
                            tenant=tenant,
                            booking=booking,
                            viewer_role=role,
                        )
                    ).data
                    for booking in bookings
                ],
            }
        )
        return api_response(request, data=response_serializer.data, status=status.HTTP_200_OK)

    @extend_schema(
        summary="后台代建预约",
        request=StaffBookingCreateRequestSerializer,
        responses={201: enveloped_response_serializer(StaffBookingResponseSerializer)},
    )
    def post(self, request, *args, **kwargs):
        """租户管理员或工作人员代建预约，需 Idempotency-Key。

        Args:
            request: DRF 请求对象。

        Returns:
            Response: 含新预约的标准 envelope 响应，HTTP 201。
        """
        idempotency_key = request.headers.get("Idempotency-Key", "").strip()
        if not idempotency_key:
            raise DRFValidationError({"idempotency_key": "必须提供 Idempotency-Key 请求头。"})

        tenant = self.get_tenant()
        role = tenant_membership_role_get_for_user(tenant=tenant, user=request.user)
        request_serializer = StaffBookingCreateRequestSerializer(data=request.data)
        request_serializer.is_valid(raise_exception=True)
        validated_data = request_serializer.validated_data

        try:
            booking = scheduling_booking_staff_create(
                tenant=tenant,
                operator=request.user,
                role=role,
                idempotency_key=idempotency_key,
                service_id=validated_data["service_id"],
                party_size=validated_data.get("party_size", 1),
                time_slot_id=validated_data["time_slot_id"],
                customer_id=validated_data.get("customer_id"),
                contact_name=validated_data.get("contact_name", ""),
                contact_phone=validated_data.get("contact_phone", ""),
            )
        except DjangoValidationError as exc:
            _raise_drf_validation_error(exc)

        response_serializer = StaffBookingResponseSerializer(
            scheduling_booking_to_dict(
                tenant=tenant,
                booking=booking,
                viewer_role=role,
            )
        )
        return api_response(
            request,
            data=response_serializer.data,
            message="created",
            status=status.HTTP_201_CREATED,
        )


class BookingCompleteView(TenantContextMixin, APIView):
    permission_classes = [RequiresTenantMembership, RequiresTenantAdmin]

    @extend_schema(
        summary="标记预约已完成",
        responses={200: enveloped_response_serializer(StaffBookingResponseSerializer)},
    )
    def post(self, request, *args, **kwargs):
        """将预约标记为 COMPLETED。

        Args:
            request: DRF 请求对象。

        Returns:
            Response: 含更新后预约的标准 envelope 响应。
        """
        tenant = self.get_tenant()
        role = tenant_membership_role_get_for_user(tenant=tenant, user=request.user)
        booking_id = self.kwargs["booking_id"]
        try:
            booking = scheduling_booking_get_for_tenant(tenant=tenant, booking_id=booking_id)
        except Booking.DoesNotExist as exc:
            raise NotFound("预约不存在。") from exc

        try:
            old_status = booking.status
            booking = scheduling_booking_complete(booking=booking)
        except DjangoValidationError as exc:
            _raise_drf_validation_error(exc)

        audit_log_booking_status_change(
            tenant=tenant,
            booking_id=booking.id,
            old_status=old_status,
            new_status=booking.status,
            request=request,
        )

        response_serializer = StaffBookingResponseSerializer(
            scheduling_booking_to_dict(
                tenant=tenant,
                booking=booking,
                viewer_role=role,
            )
        )
        return api_response(request, data=response_serializer.data, status=status.HTTP_200_OK)


class BookingNoShowView(TenantContextMixin, APIView):
    permission_classes = [RequiresTenantMembership, RequiresTenantAdmin]

    @extend_schema(
        summary="标记预约爽约",
        responses={200: enveloped_response_serializer(StaffBookingResponseSerializer)},
    )
    def post(self, request, *args, **kwargs):
        """将预约标记为 NO_SHOW。

        Args:
            request: DRF 请求对象。

        Returns:
            Response: 含更新后预约的标准 envelope 响应。
        """
        tenant = self.get_tenant()
        role = tenant_membership_role_get_for_user(tenant=tenant, user=request.user)
        booking_id = self.kwargs["booking_id"]
        try:
            booking = scheduling_booking_get_for_tenant(tenant=tenant, booking_id=booking_id)
        except Booking.DoesNotExist as exc:
            raise NotFound("预约不存在。") from exc

        try:
            old_status = booking.status
            booking = scheduling_booking_no_show(booking=booking)
        except DjangoValidationError as exc:
            _raise_drf_validation_error(exc)

        audit_log_booking_status_change(
            tenant=tenant,
            booking_id=booking.id,
            old_status=old_status,
            new_status=booking.status,
            request=request,
        )

        response_serializer = StaffBookingResponseSerializer(
            scheduling_booking_to_dict(
                tenant=tenant,
                booking=booking,
                viewer_role=role,
            )
        )
        return api_response(request, data=response_serializer.data, status=status.HTTP_200_OK)


class TimeSlotCapacityAdjustView(TenantContextMixin, APIView):
    permission_classes = [RequiresTenantMembership, RequiresTenantAdmin]

    @extend_schema(
        summary="调整固定时段容量",
        request=TimeSlotCapacityAdjustRequestSerializer,
        responses={200: enveloped_response_serializer(TimeSlotResponseSerializer)},
    )
    def post(self, request, *args, **kwargs):
        """显式调整时段容量并记录原因。

        Args:
            request: DRF 请求对象。

        Returns:
            Response: 含更新后时段的标准 envelope 响应。
        """
        tenant = self.get_tenant()
        time_slot_id = self.kwargs["time_slot_id"]
        try:
            time_slot = scheduling_time_slot_get_for_tenant(
                tenant=tenant,
                time_slot_id=time_slot_id,
            )
        except TimeSlot.DoesNotExist as exc:
            raise NotFound("固定时段不存在。") from exc

        request_serializer = TimeSlotCapacityAdjustRequestSerializer(data=request.data)
        request_serializer.is_valid(raise_exception=True)
        validated_data = request_serializer.validated_data

        try:
            http_context = audit_http_context(request=request)
            time_slot = scheduling_timeslot_capacity_adjust(
                tenant=tenant,
                time_slot=time_slot,
                capacity=validated_data["capacity"],
                reason=validated_data["reason"],
                operator=request.user,
                request_id=http_context["request_id"],
                ip_address=http_context["ip_address"],
            )
        except DjangoValidationError as exc:
            _raise_drf_validation_error(exc)

        response_serializer = TimeSlotResponseSerializer(
            scheduling_time_slot_to_dict(time_slot=time_slot)
        )
        return api_response(request, data=response_serializer.data, status=status.HTTP_200_OK)
