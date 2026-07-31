from datetime import UTC, datetime
from threading import Barrier, Thread
from uuid import uuid4
from zoneinfo import ZoneInfo

from catalog.models import Location, Resource, Service
from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import TransactionTestCase, override_settings
from rest_framework.test import APIClient, APITestCase
from scheduling.models import Booking, BookingStatus, TimeSlot, TimeSlotStatus
from tenants.models import Tenant, TenantCustomer

from tests.support import api_code, api_data, api_message


@override_settings(
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "booking-create-tests",
        }
    },
    OTP_SEND_INTERVAL_SECONDS=60,
)
class BookingCreateTests(APITestCase):
    """客户创建预约 API 测试。"""

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

        tenant_tz = ZoneInfo("Asia/Shanghai")
        slot_start = datetime(2026, 8, 1, 9, 0, tzinfo=tenant_tz).astimezone(UTC)
        slot_end = datetime(2026, 8, 1, 10, 0, tzinfo=tenant_tz).astimezone(UTC)
        self.time_slot = TimeSlot.objects.create(
            tenant=self.tenant,
            location=self.location,
            resource=self.resource,
            start=slot_start,
            end=slot_end,
            capacity=3,
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

    def _seed_booking_on_slot(self, *, party_size: int, idempotency_key: str) -> None:
        """在默认时段上创建占用容量的预约（使用另一客户）。"""
        other_phone = "13900139001"
        self.client.post(
            "/api/v1/auth/customer/verification-codes/",
            {"phone": other_phone},
            format="json",
        )
        from accounts.services.sms import sms_sent_message_list

        code = sms_sent_message_list()[-1]["code"]
        self.client.post(
            "/api/v1/auth/customer/sessions/",
            {"phone": other_phone, "code": code, "tenant_slug": "acme"},
            format="json",
        )
        other_customer = TenantCustomer.objects.get(
            user__customer_profile__phone=other_phone,
            tenant=self.tenant,
        )
        Booking.objects.create(
            tenant=self.tenant,
            customer=other_customer,
            time_slot=self.time_slot,
            service=self.service,
            status=BookingStatus.CONFIRMED,
            party_size=party_size,
            idempotency_key=idempotency_key,
        )

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
            "party_size": 1,
        }
        body.update(payload)
        if body.get("time_slot_id") is None:
            body.pop("time_slot_id", None)
        headers = {}
        if idempotency_key is not None:
            headers["HTTP_IDEMPOTENCY_KEY"] = idempotency_key
        return self.client.post(
            "/api/v1/acme/scheduling/bookings/",
            body,
            format="json",
            **headers,
        )

    def test_customer_creates_booking_with_confirmed_status(self):
        """客户指定时段、服务、人数创建预约并自动确认。"""
        response = self._create_booking(idempotency_key=str(uuid4()))

        self.assertEqual(response.status_code, 201)
        self.assertEqual(api_code(response), 0)
        data = api_data(response)
        self.assertEqual(data["status"], BookingStatus.CONFIRMED)
        self.assertEqual(data["party_size"], 1)
        self.assertEqual(data["service_id"], self.service.id)
        self.assertEqual(data["resource_id"], self.resource.id)
        self.assertEqual(data["time_slot_id"], self.time_slot.id)
        self.assertEqual(Booking.objects.count(), 1)

    def test_insufficient_capacity_returns_error_without_booking(self):
        """容量不足时返回明确错误且不产生预约记录。"""
        self._seed_booking_on_slot(party_size=2, idempotency_key="seed-booking")

        response = self._create_booking(idempotency_key=str(uuid4()), party_size=2)

        self.assertEqual(response.status_code, 400)
        self.assertIn("容量不足", api_message(response))
        self.assertEqual(Booking.objects.count(), 1)

    def test_idempotent_retry_returns_first_booking_without_double_capacity(self):
        """相同 Idempotency-Key 重试返回首次结果且不重复占用容量。"""
        idempotency_key = str(uuid4())
        first = self._create_booking(idempotency_key=idempotency_key, party_size=2)
        second = self._create_booking(idempotency_key=idempotency_key, party_size=2)

        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 201)
        self.assertEqual(api_data(first)["id"], api_data(second)["id"])
        self.assertEqual(Booking.objects.count(), 1)

    def test_same_customer_cannot_create_two_active_bookings_on_same_slot(self):
        """同一客户同一时段不能拥有两条有效预约。"""
        first = self._create_booking(idempotency_key=str(uuid4()))
        self.assertEqual(first.status_code, 201)

        second = self._create_booking(idempotency_key=str(uuid4()))
        self.assertEqual(second.status_code, 400)
        self.assertIn("已有有效预约", api_message(second))
        self.assertEqual(Booking.objects.count(), 1)

    def test_auto_assign_picks_lowest_load_resource_with_stable_id_tiebreak(self):
        """未指定资源时按最低负载与资源 ID 稳定排序自动分配。"""
        self.service.resources.remove(self.resource)
        self.time_slot.status = TimeSlotStatus.CLOSED
        self.time_slot.save(update_fields=["status"])

        heavy_resource = Resource.objects.create(
            tenant=self.tenant,
            location=self.location,
            name="Bob",
        )
        light_resource = Resource.objects.create(
            tenant=self.tenant,
            location=self.location,
            name="Carol",
        )
        self.service.resources.add(heavy_resource, light_resource)

        heavy_slot = TimeSlot.objects.create(
            tenant=self.tenant,
            location=self.location,
            resource=heavy_resource,
            start=self.time_slot.start,
            end=self.time_slot.end,
            capacity=5,
            status=TimeSlotStatus.OPEN,
        )
        TimeSlot.objects.create(
            tenant=self.tenant,
            location=self.location,
            resource=light_resource,
            start=self.time_slot.start,
            end=self.time_slot.end,
            capacity=5,
            status=TimeSlotStatus.OPEN,
        )
        customer = TenantCustomer.objects.get(user=self.customer_user, tenant=self.tenant)
        Booking.objects.create(
            tenant=self.tenant,
            customer=customer,
            time_slot=heavy_slot,
            service=self.service,
            status=BookingStatus.CONFIRMED,
            party_size=3,
            idempotency_key="heavy-load",
        )

        response = self._create_booking(
            idempotency_key=str(uuid4()),
            time_slot_id=None,
            location_id=self.location.id,
            start=self.time_slot.start.isoformat(),
            end=self.time_slot.end.isoformat(),
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(api_data(response)["resource_id"], light_resource.id)

    def test_customer_can_list_own_bookings_in_tenant(self):
        """客户可查看自己在当前租户下的预约列表。"""
        create = self._create_booking(idempotency_key=str(uuid4()))
        self.assertEqual(create.status_code, 201)
        booking_id = api_data(create)["id"]

        response = self.client.get("/api/v1/acme/scheduling/bookings/")

        self.assertEqual(response.status_code, 200)
        bookings = api_data(response)["bookings"]
        self.assertEqual(len(bookings), 1)
        self.assertEqual(bookings[0]["id"], booking_id)


class BookingCreateConcurrencyTests(TransactionTestCase):
    """并发创建预约测试。"""

    reset_sequences = True

    def setUp(self):
        """准备单容量时段与两名客户 JWT。"""
        cache.clear()
        from django.test import override_settings

        self._settings = override_settings(
            CACHES={
                "default": {
                    "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
                    "LOCATION": "booking-concurrency-tests",
                }
            },
            OTP_SEND_INTERVAL_SECONDS=60,
        )
        self._settings.enable()
        self.client = APIClient()
        self.tenant = Tenant.objects.create(slug="acme", name="Acme Corp")
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
        slot_start = datetime(2026, 8, 1, 9, 0, tzinfo=tenant_tz).astimezone(UTC)
        slot_end = datetime(2026, 8, 1, 10, 0, tzinfo=tenant_tz).astimezone(UTC)
        self.time_slot = TimeSlot.objects.create(
            tenant=self.tenant,
            location=self.location,
            resource=self.resource,
            start=slot_start,
            end=slot_end,
            capacity=1,
            status=TimeSlotStatus.OPEN,
        )
        self.tokens = []
        for phone in ("13900139002", "13900139003"):
            self.client.post(
                "/api/v1/auth/customer/verification-codes/",
                {"phone": phone},
                format="json",
            )
            from accounts.services.sms import sms_sent_message_list

            code = sms_sent_message_list()[-1]["code"]
            login = self.client.post(
                "/api/v1/auth/customer/sessions/",
                {"phone": phone, "code": code, "tenant_slug": "acme"},
                format="json",
            )
            self.tokens.append(api_data(login)["access"])

    def tearDown(self):
        """关闭并发测试 override_settings。"""
        self._settings.disable()

    def test_concurrent_creates_do_not_exceed_slot_capacity(self):
        """并发创建同一单容量时段时仅一条预约成功。"""
        results: list = []
        barrier = Barrier(2)

        def attempt(token: str) -> None:
            """并发发起创建预约请求。"""
            barrier.wait()
            client = self.client_class()
            response = client.post(
                "/api/v1/acme/scheduling/bookings/",
                {
                    "time_slot_id": self.time_slot.id,
                    "service_id": self.service.id,
                    "party_size": 1,
                },
                format="json",
                HTTP_AUTHORIZATION=f"Bearer {token}",
                HTTP_IDEMPOTENCY_KEY=str(uuid4()),
            )
            results.append(response)

        threads = [
            Thread(target=attempt, args=(self.tokens[0],)),
            Thread(target=attempt, args=(self.tokens[1],)),
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        success_count = sum(1 for response in results if response.status_code == 201)
        failure_count = sum(1 for response in results if response.status_code == 400)
        self.assertEqual(success_count, 1)
        self.assertEqual(failure_count, 1)
        self.assertEqual(Booking.objects.count(), 1)
