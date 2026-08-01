from datetime import UTC, datetime, timedelta
from unittest.mock import patch
from uuid import uuid4
from zoneinfo import ZoneInfo

from accounts.models import CustomerProfile
from catalog.models import Location, Resource, Service
from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import override_settings
from rest_framework.test import APITestCase
from scheduling.models import Booking, BookingStatus, TimeSlot, TimeSlotStatus
from scheduling.services.audit import scheduling_audit_clear_for_tests, scheduling_audit_list
from tenants.models import Tenant, TenantCustomer, TenantMembership, TenantRole

from tests.support import api_code, api_data, api_message, booking_create_for_test


@override_settings(
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "staff-booking-tests",
        }
    },
    OTP_SEND_INTERVAL_SECONDS=60,
)
class StaffBookingTests(APITestCase):
    """后台代建预约、权限边界与状态标记测试。"""

    tenant: Tenant
    location: Location
    resource: Resource
    other_resource: Resource
    service: Service
    time_slot: TimeSlot
    admin: User
    staff: User

    def setUp(self):
        """准备租户、管理员、工作人员、目录与时段。"""
        cache.clear()
        scheduling_audit_clear_for_tests()
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
        self.staff = User.objects.create_user(username="stylist", password="StrongPass123!")
        TenantMembership.objects.create(
            tenant=self.tenant,
            user=self.staff,
            role=TenantRole.STAFF,
        )

        self.location = Location.objects.create(tenant=self.tenant, name="Main Studio")
        self.resource = Resource.objects.create(
            tenant=self.tenant,
            location=self.location,
            name="Alice",
        )
        self.other_resource = Resource.objects.create(
            tenant=self.tenant,
            location=self.location,
            name="Bob",
        )
        self.service = Service.objects.create(
            tenant=self.tenant,
            location=self.location,
            name="Haircut",
            duration_minutes=60,
        )
        self.service.resources.add(self.resource, self.other_resource)

        tenant_tz = ZoneInfo("Asia/Shanghai")
        self.slot_start = datetime(2026, 8, 1, 9, 0, tzinfo=tenant_tz).astimezone(UTC)
        self.slot_end = datetime(2026, 8, 1, 10, 0, tzinfo=tenant_tz).astimezone(UTC)
        self.time_slot = TimeSlot.objects.create(
            tenant=self.tenant,
            location=self.location,
            resource=self.resource,
            start=self.slot_start,
            end=self.slot_end,
            capacity=2,
            status=TimeSlotStatus.OPEN,
        )
        self.other_slot = TimeSlot.objects.create(
            tenant=self.tenant,
            location=self.location,
            resource=self.other_resource,
            start=self.slot_start,
            end=self.slot_end,
            capacity=2,
            status=TimeSlotStatus.OPEN,
        )

        self.existing_customer_user = User.objects.create_user(username="existing-customer")
        CustomerProfile.objects.create(user=self.existing_customer_user, phone="13900139111")
        self.existing_customer = TenantCustomer.objects.create(
            tenant=self.tenant,
            user=self.existing_customer_user,
            display_name="老客户",
        )

    def _login(self, login: str) -> str:
        """后台用户登录并返回 access token。"""
        response = self.client.post(
            "/api/v1/auth/staff/sessions/",
            {"login": login, "password": "StrongPass123!"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        return api_data(response)["access"]

    def _as_admin(self) -> None:
        """切换为租户管理员凭据。"""
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self._login('tenant-admin')}")

    def _as_staff(self) -> None:
        """切换为工作人员凭据。"""
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self._login('stylist')}")

    def _staff_create_booking(self, *, idempotency_key: str | None = None, **payload):
        """调用后台代建预约 API。

        Args:
            idempotency_key (str | None): 幂等键请求头。
            **payload: 请求体字段。

        Returns:
            Response: DRF 测试客户端响应。
        """
        body = {
            "time_slot_id": self.time_slot.id,
            "service_id": self.service.id,
        }
        body.update(payload)
        headers = {}
        if idempotency_key is not None:
            headers["HTTP_IDEMPOTENCY_KEY"] = idempotency_key
        return self.client.post(
            "/api/v1/acme/scheduling/staff/bookings/",
            body,
            format="json",
            **headers,
        )

    def test_admin_creates_booking_for_existing_customer(self):
        """租户管理员可为现有客户代建预约并自动确认。"""
        self._as_admin()
        now = self.slot_start - timedelta(days=1)
        with patch("django.utils.timezone.now", return_value=now):
            response = self._staff_create_booking(
                idempotency_key=str(uuid4()),
                customer_id=self.existing_customer.id,
            )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(api_code(response), 0)
        data = api_data(response)
        self.assertEqual(data["status"], BookingStatus.CONFIRMED)
        self.assertEqual(data["customer_id"], self.existing_customer.id)
        self.assertEqual(Booking.objects.count(), 1)

    def test_admin_creates_booking_for_temp_contact_without_otp(self):
        """管理员可为临时联系人代建预约，无需 OTP。"""
        self._as_admin()
        now = self.slot_start - timedelta(days=1)
        with patch("django.utils.timezone.now", return_value=now):
            response = self._staff_create_booking(
                idempotency_key=str(uuid4()),
                contact_name="到店客户",
                contact_phone="13900139222",
            )

        self.assertEqual(response.status_code, 201)
        data = api_data(response)
        self.assertEqual(data["contact_name"], "到店客户")
        self.assertEqual(data["contact_phone"], "13900139222")
        self.assertEqual(
            TenantCustomer.objects.filter(
                tenant=self.tenant,
                user__customer_profile__phone="13900139222",
            ).count(),
            1,
        )

    def test_staff_create_records_audit_without_otp(self):
        """后台代建跳过联系人 OTP 但产生审计记录。"""
        self._as_admin()
        now = self.slot_start - timedelta(days=1)
        with patch("django.utils.timezone.now", return_value=now):
            response = self._staff_create_booking(
                idempotency_key=str(uuid4()),
                customer_id=self.existing_customer.id,
            )

        self.assertEqual(response.status_code, 201)
        booking_id = api_data(response)["id"]
        entries = scheduling_audit_list(tenant_id=self.tenant.id)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["action"], "staff_booking_create")
        self.assertEqual(entries[0]["target_id"], booking_id)
        self.assertTrue(entries[0]["details"]["skipped_contact_otp"])

    def test_staff_can_create_booking_for_any_resource(self):
        """工作人员可为任意资源代建预约（不再依赖 staff_user 绑定）。"""
        self._as_staff()
        now = self.slot_start - timedelta(days=1)
        with patch("django.utils.timezone.now", return_value=now):
            response = self._staff_create_booking(
                idempotency_key=str(uuid4()),
                time_slot_id=self.other_slot.id,
                customer_id=self.existing_customer.id,
            )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(api_data(response)["resource_id"], self.other_resource.id)

    def test_staff_can_create_booking_for_resource(self):
        """工作人员可为资源代建预约。"""
        self._as_staff()
        now = self.slot_start - timedelta(days=1)
        with patch("django.utils.timezone.now", return_value=now):
            response = self._staff_create_booking(
                idempotency_key=str(uuid4()),
                customer_id=self.existing_customer.id,
            )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(api_data(response)["resource_id"], self.resource.id)

    def test_admin_and_staff_see_all_tenant_bookings(self):
        """管理员与工作人员均可查看租户全部预约。"""
        booking_create_for_test(
            tenant=self.tenant,
            time_slot=self.time_slot,
            service=self.service,
            customer=self.existing_customer,
            idempotency_key="alice-booking",
        )
        other_customer = TenantCustomer.objects.create(
            tenant=self.tenant,
            user=User.objects.create_user(username="bob-customer"),
        )
        booking_create_for_test(
            tenant=self.tenant,
            time_slot=self.other_slot,
            service=self.service,
            customer=other_customer,
            idempotency_key="bob-booking",
        )

        self._as_admin()
        admin_response = self.client.get("/api/v1/acme/scheduling/staff/bookings/")
        self.assertEqual(admin_response.status_code, 200)
        self.assertEqual(len(api_data(admin_response)["bookings"]), 2)

        self._as_staff()
        staff_response = self.client.get("/api/v1/acme/scheduling/staff/bookings/")
        self.assertEqual(staff_response.status_code, 200)
        staff_bookings = api_data(staff_response)["bookings"]
        self.assertEqual(len(staff_bookings), 2)

    def test_over_capacity_staff_create_rejected(self):
        """剩余名额不足时代建被拒绝。"""
        self.time_slot.capacity = 1
        self.time_slot.save(update_fields=["capacity"])
        self._as_admin()
        booking_create_for_test(
            tenant=self.tenant,
            time_slot=self.time_slot,
            service=self.service,
            idempotency_key="fill-slot",
        )
        now = self.slot_start - timedelta(days=1)
        with patch("django.utils.timezone.now", return_value=now):
            response = self._staff_create_booking(
                idempotency_key=str(uuid4()),
                customer_id=self.existing_customer.id,
            )

        self.assertEqual(response.status_code, 400)
        self.assertIn("剩余名额不足", api_message(response))
        self.assertEqual(Booking.objects.count(), 1)

    def test_admin_adjusts_capacity_then_creates_booking(self):
        """管理员调整容量并填写原因后可代建。"""
        self.time_slot.capacity = 1
        self.time_slot.save(update_fields=["capacity"])
        self._as_admin()
        booking_create_for_test(
            tenant=self.tenant,
            time_slot=self.time_slot,
            service=self.service,
            idempotency_key="fill-slot",
        )

        adjust = self.client.post(
            f"/api/v1/acme/scheduling/time-slots/{self.time_slot.id}/capacity-adjust/",
            {"capacity": 2, "reason": "临时加开"},
            format="json",
        )
        self.assertEqual(adjust.status_code, 200)
        self.assertEqual(api_data(adjust)["capacity"], 2)

        capacity_entries = [
            entry
            for entry in scheduling_audit_list(tenant_id=self.tenant.id)
            if entry["action"] == "capacity_adjust"
        ]
        self.assertEqual(len(capacity_entries), 1)
        self.assertEqual(capacity_entries[0]["details"]["reason"], "临时加开")

        now = self.slot_start - timedelta(days=1)
        with patch("django.utils.timezone.now", return_value=now):
            response = self._staff_create_booking(
                idempotency_key=str(uuid4()),
                customer_id=self.existing_customer.id,
            )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(Booking.objects.count(), 2)

    def test_admin_marks_booking_completed(self):
        """租户管理员可将预约标记为 COMPLETED。"""
        booking = booking_create_for_test(
            tenant=self.tenant,
            time_slot=self.time_slot,
            service=self.service,
            customer=self.existing_customer,
            status=BookingStatus.CONFIRMED,
            idempotency_key="complete-me",
        )
        self._as_admin()
        response = self.client.post(
            f"/api/v1/acme/scheduling/bookings/{booking.id}/complete/",
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(api_data(response)["status"], BookingStatus.COMPLETED)
        booking.refresh_from_db()
        self.assertEqual(booking.status, BookingStatus.COMPLETED)

    def test_admin_marks_booking_no_show(self):
        """租户管理员可将预约标记为 NO_SHOW。"""
        booking = booking_create_for_test(
            tenant=self.tenant,
            time_slot=self.time_slot,
            service=self.service,
            customer=self.existing_customer,
            status=BookingStatus.CONFIRMED,
            idempotency_key="no-show-me",
        )
        self._as_admin()
        response = self.client.post(
            f"/api/v1/acme/scheduling/bookings/{booking.id}/no-show/",
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(api_data(response)["status"], BookingStatus.NO_SHOW)
        booking.refresh_from_db()
        self.assertEqual(booking.status, BookingStatus.NO_SHOW)

    def test_staff_sees_masked_phone_admin_sees_full_phone(self):
        """工作人员看到脱敏手机号，管理员看到完整号码。"""
        booking = booking_create_for_test(
            tenant=self.tenant,
            time_slot=self.time_slot,
            service=self.service,
            customer=self.existing_customer,
            idempotency_key="phone-mask",
        )
        booking.contact_phone = "13800138000"
        booking.save(update_fields=["contact_phone"])

        self._as_staff()
        staff_response = self.client.get("/api/v1/acme/scheduling/staff/bookings/")
        staff_data = api_data(staff_response)["bookings"][0]
        self.assertEqual(staff_data["contact_phone"], "138****8000")
        self.assertEqual(staff_data["customer_phone"], "139****9111")

        self._as_admin()
        admin_response = self.client.get("/api/v1/acme/scheduling/staff/bookings/")
        admin_data = api_data(admin_response)["bookings"][0]
        self.assertEqual(admin_data["contact_phone"], "13800138000")
        self.assertEqual(admin_data["customer_phone"], "13900139111")
