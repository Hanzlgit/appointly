from datetime import UTC, datetime, timedelta
from unittest.mock import patch
from uuid import uuid4
from zoneinfo import ZoneInfo

from catalog.models import Location, Resource, Service
from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import override_settings
from rest_framework.test import APITestCase
from scheduling.constants import (
    DEFAULT_CANCEL_DEADLINE_MINUTES,
    DEFAULT_CONFIRMATION_MODE,
    DEFAULT_FUTURE_BOOKING_LIMIT,
    DEFAULT_MAX_BOOKING_WINDOW_DAYS,
    DEFAULT_MIN_ADVANCE_MINUTES,
    DEFAULT_PENDING_RETENTION_MINUTES,
    BookingConfirmationMode,
)
from scheduling.models import Booking, BookingStatus, TimeSlot, TimeSlotStatus
from scheduling.tasks import scheduling_expire_pending_bookings
from tenants.models import Tenant, TenantCustomer, TenantMembership, TenantRole

from tests.support import api_code, api_data, api_message, booking_create_for_test


@override_settings(
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "booking-rules-tests",
        }
    },
    OTP_SEND_INTERVAL_SECONDS=60,
)
class BookingRulesTests(APITestCase):
    """租户预约业务规则与状态机测试。"""

    tenant: Tenant
    admin: User
    location: Location
    resource: Resource
    service: Service
    time_slot: TimeSlot

    def setUp(self):
        """准备租户、管理员、客户、目录与时段。"""
        cache.clear()
        self.tenant = Tenant.objects.create(
            slug="acme",
            name="Acme Corp",
            timezone="Asia/Shanghai",
        )
        self.admin = User.objects.create_user(username="tenant-admin", password="StrongPass123!")
        TenantMembership.objects.create(
            tenant=self.tenant,
            user=self.admin,
            role=TenantRole.TENANT_ADMIN,
        )
        self.location = Location.objects.create(tenant=self.tenant, name="Main Studio")
        self.resource = Resource.objects.create(
            tenant=self.tenant,
            location=self.location,
            name="Alice",
        )
        self.service = Service.objects.create(
            tenant=self.tenant,
            location=self.location,
            name="Haircut",
            duration_minutes=60,
        )
        self.service.resources.add(self.resource)

        tenant_tz = ZoneInfo("Asia/Shanghai")
        self.slot_start = datetime(2026, 8, 1, 9, 0, tzinfo=tenant_tz).astimezone(UTC)
        self.slot_end = datetime(2026, 8, 1, 10, 0, tzinfo=tenant_tz).astimezone(UTC)
        self.time_slot = TimeSlot.objects.create(
            tenant=self.tenant,
            location=self.location,
            resource=self.resource,
            start=self.slot_start,
            end=self.slot_end,
            capacity=1,
            status=TimeSlotStatus.OPEN,
        )

        self._login_admin()
        self._login_customer()

    def _login_admin(self) -> None:
        """租户管理员登录并设置 Bearer 凭据。"""
        login = self.client.post(
            "/api/v1/auth/staff/sessions/",
            {"login": "tenant-admin", "password": "StrongPass123!"},
            format="json",
        )
        access = api_data(login)["access"]
        self.admin_token = access

    def _login_customer(self) -> None:
        """客户 OTP 登录并保存 Bearer 凭据。"""
        self.phone = "13900139000"
        self.client.post(
            "/api/v1/auth/customer/verification-codes/",
            {"phone": self.phone},
            format="json",
        )
        from accounts.services.sms import sms_sent_message_list

        code = sms_sent_message_list()[-1]["code"]
        login = self.client.post(
            "/api/v1/auth/customer/sessions/",
            {"phone": self.phone, "code": code, "tenant_slug": "acme"},
            format="json",
        )
        self.customer_token = api_data(login)["access"]
        self.customer_user = User.objects.get(customer_profile__phone=self.phone)

    def _as_admin(self) -> None:
        """切换为管理员凭据。"""
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.admin_token}")

    def _as_customer(self) -> None:
        """切换为客户凭据。"""
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.customer_token}")

    def _update_booking_settings(self, **payload) -> dict:
        """调用管理员更新预约规则 API。

        Args:
            **payload: 请求体字段。

        Returns:
            dict: envelope 解析后的 ``data``。
        """
        self._as_admin()
        response = self.client.patch(
            "/api/v1/acme/scheduling/booking-settings/",
            payload,
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        return api_data(response)

    def _create_booking(self, *, idempotency_key: str | None = None, **payload):
        """客户创建预约。

        Args:
            idempotency_key (str | None): 幂等键。
            **payload: 请求体字段。

        Returns:
            Response: DRF 测试客户端响应。
        """
        self._as_customer()
        body = {
            "time_slot_id": self.time_slot.id,
            "service_id": self.service.id,
            "party_size": 1,
        }
        body.update(payload)
        headers = {}
        if idempotency_key is not None:
            headers["HTTP_IDEMPOTENCY_KEY"] = idempotency_key
        return self.client.post(
            "/api/v1/acme/scheduling/bookings/",
            body,
            format="json",
            **headers,
        )

    def test_admin_can_get_default_booking_settings(self):
        """租户管理员可读取默认预约业务规则。"""
        self._as_admin()
        response = self.client.get("/api/v1/acme/scheduling/booking-settings/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(api_code(response), 0)
        settings = api_data(response)
        self.assertEqual(settings["min_advance_minutes"], DEFAULT_MIN_ADVANCE_MINUTES)
        self.assertEqual(settings["max_booking_window_days"], DEFAULT_MAX_BOOKING_WINDOW_DAYS)
        self.assertEqual(settings["pending_retention_minutes"], DEFAULT_PENDING_RETENTION_MINUTES)
        self.assertEqual(settings["cancel_deadline_minutes"], DEFAULT_CANCEL_DEADLINE_MINUTES)
        self.assertEqual(settings["future_booking_limit"], DEFAULT_FUTURE_BOOKING_LIMIT)
        self.assertEqual(settings["confirmation_mode"], DEFAULT_CONFIRMATION_MODE)

    def test_admin_can_update_booking_settings(self):
        """租户管理员可更新预约业务规则。"""
        updated = self._update_booking_settings(
            min_advance_minutes=120,
            max_booking_window_days=14,
            pending_retention_minutes=45,
            cancel_deadline_minutes=60,
            future_booking_limit=3,
            confirmation_mode=BookingConfirmationMode.MANUAL,
        )

        self.assertEqual(updated["min_advance_minutes"], 120)
        self.assertEqual(updated["max_booking_window_days"], 14)
        self.assertEqual(updated["pending_retention_minutes"], 45)
        self.assertEqual(updated["cancel_deadline_minutes"], 60)
        self.assertEqual(updated["future_booking_limit"], 3)
        self.assertEqual(updated["confirmation_mode"], BookingConfirmationMode.MANUAL)

    def test_settings_outside_platform_bounds_are_rejected(self):
        """超出平台上下限的配置更新被拒绝。"""
        self._as_admin()
        response = self.client.patch(
            "/api/v1/acme/scheduling/booking-settings/",
            {"min_advance_minutes": 999999},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("min_advance_minutes", api_message(response))

    def test_auto_confirm_creates_confirmed_booking(self):
        """自动确认模式下创建预约直接进入 CONFIRMED。"""
        now = self.slot_start - timedelta(days=1)
        with patch("django.utils.timezone.now", return_value=now):
            response = self._create_booking(idempotency_key=str(uuid4()))

        self.assertEqual(response.status_code, 201)
        self.assertEqual(api_data(response)["status"], BookingStatus.CONFIRMED)

    def test_manual_confirm_creates_pending_and_preoccupies_capacity(self):
        """人工确认模式下创建 PENDING 并预占容量。"""
        self._update_booking_settings(confirmation_mode=BookingConfirmationMode.MANUAL)
        now = self.slot_start - timedelta(days=1)
        with patch("django.utils.timezone.now", return_value=now):
            first = self._create_booking(idempotency_key=str(uuid4()))

        self.assertEqual(first.status_code, 201)
        self.assertEqual(api_data(first)["status"], BookingStatus.PENDING)

        other_phone = "13900139099"
        self.client.post(
            "/api/v1/auth/customer/verification-codes/",
            {"phone": other_phone},
            format="json",
        )
        from accounts.services.sms import sms_sent_message_list

        code = sms_sent_message_list()[-1]["code"]
        login = self.client.post(
            "/api/v1/auth/customer/sessions/",
            {"phone": other_phone, "code": code, "tenant_slug": "acme"},
            format="json",
        )
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {api_data(login)['access']}")
        with patch("django.utils.timezone.now", return_value=now):
            second = self.client.post(
                "/api/v1/acme/scheduling/bookings/",
                {
                    "time_slot_id": self.time_slot.id,
                    "service_id": self.service.id,
                    "party_size": 1,
                },
                format="json",
                HTTP_IDEMPOTENCY_KEY=str(uuid4()),
            )

        self.assertEqual(second.status_code, 400)
        self.assertIn("容量不足", api_message(second))

    def test_booking_before_min_advance_is_rejected(self):
        """早于最短提前预约时间的预约被拒绝。"""
        self._update_booking_settings(min_advance_minutes=120)
        now = self.slot_start - timedelta(minutes=30)
        with patch("django.utils.timezone.now", return_value=now):
            response = self._create_booking(idempotency_key=str(uuid4()))

        self.assertEqual(response.status_code, 400)
        self.assertIn("最短提前预约", api_message(response))

    def test_booking_beyond_max_window_is_rejected(self):
        """超出最远可预约范围的预约被拒绝。"""
        self._update_booking_settings(max_booking_window_days=7)
        now = self.slot_start - timedelta(days=10)
        with patch("django.utils.timezone.now", return_value=now):
            response = self._create_booking(idempotency_key=str(uuid4()))

        self.assertEqual(response.status_code, 400)
        self.assertIn("最远可预约", api_message(response))

    def test_future_booking_limit_is_enforced(self):
        """超过客户未来有效预约上限时被拒绝。"""
        self._update_booking_settings(future_booking_limit=1)
        customer = TenantCustomer.objects.get(user=self.customer_user, tenant=self.tenant)
        other_slot = TimeSlot.objects.create(
            tenant=self.tenant,
            location=self.location,
            resource=self.resource,
            start=self.slot_start + timedelta(days=1),
            end=self.slot_end + timedelta(days=1),
            capacity=5,
            status=TimeSlotStatus.OPEN,
        )
        now = self.slot_start - timedelta(days=2)
        with patch("django.utils.timezone.now", return_value=now):
            booking_create_for_test(
                tenant=self.tenant,
                time_slot=other_slot,
                customer=customer,
                idempotency_key="existing-future",
            )
            response = self._create_booking(idempotency_key=str(uuid4()))

        self.assertEqual(response.status_code, 400)
        self.assertIn("未来有效预约", api_message(response))

    def test_admin_confirms_pending_booking(self):
        """管理员可将待确认预约确认为 CONFIRMED。"""
        self._update_booking_settings(confirmation_mode=BookingConfirmationMode.MANUAL)
        now = self.slot_start - timedelta(days=1)
        with patch("django.utils.timezone.now", return_value=now):
            create = self._create_booking(idempotency_key=str(uuid4()))
        booking_id = api_data(create)["id"]

        self._as_admin()
        response = self.client.post(
            f"/api/v1/acme/scheduling/bookings/{booking_id}/confirm/",
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(api_data(response)["status"], BookingStatus.CONFIRMED)
        self.assertEqual(Booking.objects.get(id=booking_id).status, BookingStatus.CONFIRMED)

    def test_admin_rejects_pending_booking_and_releases_capacity(self):
        """管理员拒绝待确认预约后释放容量。"""
        self._update_booking_settings(confirmation_mode=BookingConfirmationMode.MANUAL)
        now = self.slot_start - timedelta(days=1)
        with patch("django.utils.timezone.now", return_value=now):
            create = self._create_booking(idempotency_key=str(uuid4()))
        booking_id = api_data(create)["id"]

        self._as_admin()
        reject = self.client.post(
            f"/api/v1/acme/scheduling/bookings/{booking_id}/reject/",
            format="json",
        )
        self.assertEqual(reject.status_code, 200)
        self.assertEqual(api_data(reject)["status"], BookingStatus.REJECTED)

        retry = self._create_booking(idempotency_key=str(uuid4()))
        self.assertEqual(retry.status_code, 201)

    def test_expired_pending_booking_releases_capacity(self):
        """超时 PENDING 预约进入 EXPIRED 并释放容量。"""
        self._update_booking_settings(
            confirmation_mode=BookingConfirmationMode.MANUAL,
            pending_retention_minutes=30,
        )
        created_at = self.slot_start - timedelta(days=1)
        with patch("django.utils.timezone.now", return_value=created_at):
            create = self._create_booking(idempotency_key=str(uuid4()))
        booking_id = api_data(create)["id"]
        booking = Booking.objects.get(id=booking_id)
        self.assertEqual(booking.status, BookingStatus.PENDING)

        expired_now = created_at + timedelta(minutes=31)
        with patch("django.utils.timezone.now", return_value=expired_now):
            expired_count = scheduling_expire_pending_bookings()

        self.assertEqual(expired_count, 1)
        booking.refresh_from_db()
        self.assertEqual(booking.status, BookingStatus.EXPIRED)

        retry = self._create_booking(idempotency_key=str(uuid4()))
        self.assertEqual(retry.status_code, 201)
