from datetime import timedelta
from unittest.mock import patch
from uuid import uuid4

from catalog.models import Location, Resource, Service
from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APITestCase
from scheduling.models import Booking, BookingCancelActor, BookingStatus, TimeSlot, TimeSlotStatus
from tenants.models import Tenant, TenantCustomer

from tests.support import api_code, api_data, api_message


@override_settings(
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "booking-lifecycle-tests",
        }
    },
    OTP_SEND_INTERVAL_SECONDS=60,
)
class BookingLifecycleTests(APITestCase):
    """客户预约生命周期（取消、改期、人数与联系人）测试。"""

    tenant: Tenant
    location: Location
    resource: Resource
    service: Service
    time_slot: TimeSlot
    customer_user: User

    def setUp(self):
        """准备租户、目录、时段与客户 JWT。"""
        cache.clear()
        self.tenant = Tenant.objects.create(
            slug="acme",
            name="Acme Corp",
            timezone="Asia/Shanghai",
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

        self.slot_start = timezone.now() + timedelta(days=2)
        self.slot_end = self.slot_start + timedelta(hours=1)
        self.time_slot = TimeSlot.objects.create(
            tenant=self.tenant,
            location=self.location,
            resource=self.resource,
            start=self.slot_start,
            end=self.slot_end,
            capacity=1,
            status=TimeSlotStatus.OPEN,
        )
        self.other_slot = TimeSlot.objects.create(
            tenant=self.tenant,
            location=self.location,
            resource=self.resource,
            start=self.slot_start + timedelta(days=1),
            end=self.slot_end + timedelta(days=1),
            capacity=2,
            status=TimeSlotStatus.OPEN,
        )

        self.phone = "13900139000"
        self._login_customer()

    def _login_customer(self) -> None:
        """发送 OTP 并登录，设置 Bearer 凭据。"""
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
        access = api_data(login)["access"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
        self.customer_user = User.objects.get(customer_profile__phone=self.phone)

    def _create_booking(self, *, idempotency_key: str | None = None, **payload):
        """调用创建预约 API。

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
            "/api/v1/acme/scheduling/bookings/",
            body,
            format="json",
            **headers,
        )

    def _seed_confirmed_booking(self, *, idempotency_key: str = "seed-booking") -> Booking:
        """在默认时段创建已确认预约并返回实例。"""
        now = self.slot_start - timedelta(days=1)
        with patch("django.utils.timezone.now", return_value=now):
            response = self._create_booking(idempotency_key=idempotency_key)
        self.assertEqual(response.status_code, 201)
        return Booking.objects.get(id=api_data(response)["id"])

    def test_customer_can_cancel_before_deadline_and_releases_capacity(self):
        """客户在最晚取消时间前取消预约并释放容量。"""
        booking = self._seed_confirmed_booking()
        now = self.slot_start - timedelta(hours=3)
        with patch("django.utils.timezone.now", return_value=now):
            response = self.client.post(
                f"/api/v1/acme/scheduling/bookings/{booking.id}/cancel/",
                {"reason": "计划有变"},
                format="json",
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(api_code(response), 0)
        self.assertEqual(api_data(response)["status"], BookingStatus.CANCELLED)

        booking.refresh_from_db()
        self.assertEqual(booking.status, BookingStatus.CANCELLED)
        self.assertEqual(booking.cancel_actor, BookingCancelActor.CUSTOMER)
        self.assertEqual(booking.cancel_reason, "计划有变")
        self.assertEqual(booking.cancel_operator_id, self.customer_user.id)

        retry = self._create_booking(idempotency_key=str(uuid4()))
        self.assertEqual(retry.status_code, 201)

    def test_customer_cannot_cancel_after_deadline(self):
        """超过最晚取消时间后客户无法自行取消。"""
        booking = self._seed_confirmed_booking()
        now = self.slot_start - timedelta(minutes=30)
        with patch("django.utils.timezone.now", return_value=now):
            response = self.client.post(
                f"/api/v1/acme/scheduling/bookings/{booking.id}/cancel/",
                {"reason": "太晚了"},
                format="json",
            )

        self.assertEqual(response.status_code, 400)
        self.assertIn("最晚取消", api_message(response))
        booking.refresh_from_db()
        self.assertEqual(booking.status, BookingStatus.CONFIRMED)

    def test_customer_can_reschedule_to_new_slot(self):
        """客户改期后旧预约 RESCHEDULED 并关联新预约。"""
        booking = self._seed_confirmed_booking()
        now = self.slot_start - timedelta(days=1)
        with patch("django.utils.timezone.now", return_value=now):
            response = self.client.post(
                f"/api/v1/acme/scheduling/bookings/{booking.id}/reschedule/",
                {
                    "time_slot_id": self.other_slot.id,
                    "idempotency_key": str(uuid4()),
                },
                format="json",
            )

        self.assertEqual(response.status_code, 200)
        new_data = api_data(response)
        self.assertEqual(new_data["time_slot_id"], self.other_slot.id)
        self.assertEqual(new_data["status"], BookingStatus.CONFIRMED)

        booking.refresh_from_db()
        self.assertEqual(booking.status, BookingStatus.RESCHEDULED)
        self.assertEqual(booking.rescheduled_to_id, new_data["id"])

        new_booking = Booking.objects.get(id=new_data["id"])
        self.assertEqual(new_booking.rescheduled_from_id, booking.id)

    def test_reschedule_rollback_when_new_slot_unavailable(self):
        """新时段失败时旧预约保持不变。"""
        booking = self._seed_confirmed_booking()
        self.other_slot.capacity = 1
        self.other_slot.save(update_fields=["capacity"])
        other_customer = TenantCustomer.objects.create(
            tenant=self.tenant,
            user=User.objects.create_user(username="other-customer"),
        )
        Booking.objects.create(
            tenant=self.tenant,
            customer=other_customer,
            time_slot=self.other_slot,
            service=self.service,
            status=BookingStatus.CONFIRMED,
            idempotency_key="fill-other-slot",
        )

        now = self.slot_start - timedelta(days=1)
        with patch("django.utils.timezone.now", return_value=now):
            response = self.client.post(
                f"/api/v1/acme/scheduling/bookings/{booking.id}/reschedule/",
                {
                    "time_slot_id": self.other_slot.id,
                    "idempotency_key": str(uuid4()),
                },
                format="json",
            )

        self.assertEqual(response.status_code, 400)
        self.assertIn("剩余名额不足", api_message(response))
        booking.refresh_from_db()
        self.assertEqual(booking.status, BookingStatus.CONFIRMED)
        self.assertIsNone(booking.rescheduled_to_id)
        self.assertEqual(Booking.objects.filter(status=BookingStatus.RESCHEDULED).count(), 0)

    def test_create_booking_uses_customer_profile_contact(self):
        """创建预约时自动写入登录客户的联系人信息。"""
        customer = TenantCustomer.objects.get(user=self.customer_user, tenant=self.tenant)
        customer.display_name = "王五"
        customer.save(update_fields=["display_name", "updated_at"])
        now = self.slot_start - timedelta(days=1)
        with patch("django.utils.timezone.now", return_value=now):
            response = self._create_booking(idempotency_key=str(uuid4()))

        self.assertEqual(response.status_code, 201)
        data = api_data(response)
        self.assertEqual(data["contact_name"], "王五")
        self.assertEqual(data["contact_phone"], self.phone)

    def test_contact_phone_change_requires_otp(self):
        """修改联系人手机号需 OTP 二次验证。"""
        now = self.slot_start - timedelta(days=1)
        with patch("django.utils.timezone.now", return_value=now):
            create = self._create_booking(
                idempotency_key=str(uuid4()),
            )
        booking_id = api_data(create)["id"]

        response = self.client.patch(
            f"/api/v1/acme/scheduling/bookings/{booking_id}/contact/",
            {"contact_name": "李四", "contact_phone": "13800138002"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("验证码", api_message(response))

        self.client.post(
            "/api/v1/auth/customer/verification-codes/",
            {"phone": "13800138002"},
            format="json",
        )
        from accounts.services.sms import sms_sent_message_list

        code = sms_sent_message_list()[-1]["code"]
        response = self.client.patch(
            f"/api/v1/acme/scheduling/bookings/{booking_id}/contact/",
            {
                "contact_name": "李四",
                "contact_phone": "13800138002",
                "otp_code": code,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(api_data(response)["contact_phone"], "13800138002")

    def test_started_terminal_and_archived_bookings_not_modifiable(self):
        """已开始、终态或归档预约不可由客户修改。"""
        booking = self._seed_confirmed_booking()

        for status in (
            BookingStatus.STARTED,
            BookingStatus.CANCELLED,
            BookingStatus.RESCHEDULED,
        ):
            booking.status = status
            booking.save(update_fields=["status", "updated_at"])
            response = self.client.patch(
                f"/api/v1/acme/scheduling/bookings/{booking.id}/contact/",
                {"contact_name": "新名字"},
                format="json",
            )
            self.assertEqual(response.status_code, 400, msg=status)

        booking.status = BookingStatus.CONFIRMED
        booking.archived_at = self.slot_start
        booking.save(update_fields=["status", "archived_at", "updated_at"])
        response = self.client.post(
            f"/api/v1/acme/scheduling/bookings/{booking.id}/cancel/",
            {"reason": "归档后"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("归档", api_message(response))

    def test_illegal_state_transition_rejected(self):
        """状态机拒绝非法跳转（如已取消预约再次取消）。"""
        booking = self._seed_confirmed_booking()
        booking.status = BookingStatus.CANCELLED
        booking.save(update_fields=["status", "updated_at"])

        response = self.client.post(
            f"/api/v1/acme/scheduling/bookings/{booking.id}/cancel/",
            {"reason": "重复取消"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("不可修改", api_message(response))
