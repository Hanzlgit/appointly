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
from tenants.models import Tenant, TenantCustomer, TenantMembership, TenantRole

from tests.support import api_data, booking_create_for_test


@override_settings(
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "audit-dashboard-tests",
        }
    },
)
class AuditDashboardTests(APITestCase):
    """审计日志与经营看板 API 测试。"""

    tenant: Tenant
    location: Location
    other_location: Location
    resource: Resource
    other_resource: Resource
    service: Service
    other_service: Service
    time_slot: TimeSlot
    admin: User
    staff: User

    def setUp(self):
        """准备租户、用户、目录与时段。"""
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
        self.staff = User.objects.create_user(username="stylist", password="StrongPass123!")
        TenantMembership.objects.create(
            tenant=self.tenant,
            user=self.staff,
            role=TenantRole.STAFF,
        )

        self.location = Location.objects.create(tenant=self.tenant, name="Main Studio")
        self.other_location = Location.objects.create(tenant=self.tenant, name="Branch")
        self.resource = Resource.objects.create(
            tenant=self.tenant,
            name="Alice",
            resource_type="staff",
            staff_user=self.staff,
        )
        self.other_resource = Resource.objects.create(
            tenant=self.tenant,
            name="Bob",
            resource_type="staff",
        )
        self.location.resources.add(self.resource)
        self.other_location.resources.add(self.other_resource)

        self.service = Service.objects.create(
            tenant=self.tenant,
            name="Haircut",
            duration_minutes=60,
        )
        self.other_service = Service.objects.create(
            tenant=self.tenant,
            name="Color",
            duration_minutes=90,
        )
        self.service.resources.add(self.resource)
        self.other_service.resources.add(self.other_resource)

        tenant_tz = ZoneInfo("Asia/Shanghai")
        self.reference_date = datetime(2026, 7, 26, tzinfo=tenant_tz).date()
        self.slot_start = datetime(2026, 7, 26, 9, 0, tzinfo=tenant_tz).astimezone(UTC)
        self.slot_end = datetime(2026, 7, 26, 10, 0, tzinfo=tenant_tz).astimezone(UTC)
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
            location=self.other_location,
            resource=self.other_resource,
            start=self.slot_start,
            end=self.slot_end,
            capacity=1,
            status=TimeSlotStatus.OPEN,
        )

        customer_user = User.objects.create_user(username="customer-one")
        CustomerProfile.objects.create(user=customer_user, phone="13900139111")
        self.customer = TenantCustomer.objects.create(
            tenant=self.tenant,
            user=customer_user,
            display_name="客户甲",
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

    def test_booking_confirm_creates_audit_log_with_status_change(self):
        """确认预约时产生含前后状态的审计记录。"""
        booking = booking_create_for_test(
            tenant=self.tenant,
            time_slot=self.time_slot,
            service=self.service,
            customer=self.customer,
            status=BookingStatus.PENDING,
            idempotency_key="pending-audit",
        )
        self._as_admin()
        response = self.client.post(
            f"/api/v1/acme/scheduling/bookings/{booking.id}/confirm/",
            format="json",
            HTTP_X_REQUEST_ID="req-confirm-001",
        )
        self.assertEqual(response.status_code, 200)

        audit_response = self.client.get("/api/v1/acme/audit/logs/")
        self.assertEqual(audit_response.status_code, 200)
        logs = api_data(audit_response)["logs"]
        status_logs = [log for log in logs if log["action"] == "booking_status_change"]
        self.assertEqual(len(status_logs), 1)
        entry = status_logs[0]
        self.assertEqual(entry["target_type"], "booking")
        self.assertEqual(entry["target_id"], booking.id)
        self.assertEqual(entry["before_value"]["status"], BookingStatus.PENDING)
        self.assertEqual(entry["after_value"]["status"], BookingStatus.CONFIRMED)
        self.assertEqual(entry["operator_id"], self.admin.id)
        self.assertEqual(entry["request_id"], "req-confirm-001")

    def test_capacity_adjust_creates_audit_with_before_after(self):
        """容量调整产生含前后容量的审计记录。"""
        self._as_admin()
        response = self.client.post(
            f"/api/v1/acme/scheduling/time-slots/{self.time_slot.id}/capacity-adjust/",
            {"capacity": 4, "reason": "加开席位"},
            format="json",
            HTTP_X_REQUEST_ID="req-capacity-001",
        )
        self.assertEqual(response.status_code, 200)

        audit_response = self.client.get("/api/v1/acme/audit/logs/?action=capacity_adjust")
        logs = api_data(audit_response)["logs"]
        self.assertEqual(len(logs), 1)
        entry = logs[0]
        self.assertEqual(entry["before_value"]["capacity"], 2)
        self.assertEqual(entry["after_value"]["capacity"], 4)
        self.assertEqual(entry["details"]["reason"], "加开席位")

    def test_schedule_rule_update_creates_audit_log(self):
        """排班规则变更产生审计记录。"""
        from scheduling.models import ScheduleRule

        rule = ScheduleRule.objects.create(
            tenant=self.tenant,
            location=self.location,
            resource=self.resource,
            days_of_week=[0, 1, 2],
            start_time=datetime(2026, 1, 1, 9, 0).time(),
            end_time=datetime(2026, 1, 1, 18, 0).time(),
            capacity=2,
        )
        self._as_admin()
        response = self.client.patch(
            f"/api/v1/acme/scheduling/rules/{rule.id}/",
            {
                "effective_date": "2026-08-01",
                "capacity": 3,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200)

        audit_response = self.client.get("/api/v1/acme/audit/logs/?action=schedule_change")
        logs = api_data(audit_response)["logs"]
        self.assertEqual(len(logs), 1)
        self.assertEqual(logs[0]["target_type"], "schedule_rule")
        self.assertEqual(logs[0]["before_value"]["capacity"], 2)
        self.assertEqual(logs[0]["after_value"]["capacity"], 3)

    def test_staff_booking_create_records_sensitive_phone_in_audit(self):
        """后台代建写入含手机号的审计，工作人员读取时脱敏。"""
        self._as_admin()
        now = self.slot_start - timedelta(days=1)
        with patch("django.utils.timezone.now", return_value=now):
            create_response = self.client.post(
                "/api/v1/acme/scheduling/staff/bookings/",
                {
                    "time_slot_id": self.time_slot.id,
                    "service_id": self.service.id,
                    "party_size": 1,
                    "customer_id": self.customer.id,
                },
                format="json",
                HTTP_IDEMPOTENCY_KEY=str(uuid4()),
            )
        self.assertEqual(create_response.status_code, 201)

        self._as_staff()
        audit_response = self.client.get("/api/v1/acme/audit/logs/?action=staff_booking_create")
        self.assertEqual(audit_response.status_code, 200)
        entry = api_data(audit_response)["logs"][0]
        self.assertEqual(entry["details"]["contact_phone"], "139****9111")

        self._as_admin()
        admin_audit = self.client.get("/api/v1/acme/audit/logs/?action=staff_booking_create")
        admin_entry = api_data(admin_audit)["logs"][0]
        self.assertEqual(admin_entry["details"]["contact_phone"], "13900139111")

    def test_admin_viewing_staff_bookings_records_sensitive_view(self):
        """管理员查看含手机号的预约列表时产生敏感查看审计。"""
        booking_create_for_test(
            tenant=self.tenant,
            time_slot=self.time_slot,
            service=self.service,
            customer=self.customer,
            idempotency_key="sensitive-view",
        )
        self._as_admin()
        response = self.client.get("/api/v1/acme/scheduling/staff/bookings/")
        self.assertEqual(response.status_code, 200)

        audit_response = self.client.get("/api/v1/acme/audit/logs/?action=sensitive_view")
        logs = api_data(audit_response)["logs"]
        self.assertEqual(len(logs), 1)
        self.assertEqual(logs[0]["target_type"], "booking_list")

    def test_unauthenticated_cannot_list_audit_logs(self):
        """未认证用户无法读取审计日志。"""
        response = self.client.get("/api/v1/acme/audit/logs/")
        self.assertEqual(response.status_code, 401)

    def test_dashboard_returns_today_status_summary(self):
        """看板返回今日各状态预约数量。"""
        booking_create_for_test(
            tenant=self.tenant,
            time_slot=self.time_slot,
            service=self.service,
            customer=self.customer,
            status=BookingStatus.CONFIRMED,
            idempotency_key="dash-confirmed",
        )
        booking_create_for_test(
            tenant=self.tenant,
            time_slot=self.time_slot,
            service=self.service,
            customer=self.customer,
            status=BookingStatus.COMPLETED,
            idempotency_key="dash-completed",
        )
        self._as_admin()
        response = self.client.get(
            "/api/v1/acme/dashboard/summary/",
            {"date": "2026-07-26"},
        )
        self.assertEqual(response.status_code, 200)
        summary = api_data(response)["today_summary"]
        self.assertEqual(summary["confirmed"], 1)
        self.assertEqual(summary["completed"], 1)

    def test_dashboard_seven_day_trend_counts_future_bookings(self):
        """看板返回未来七天预约趋势。"""
        tenant_tz = ZoneInfo("Asia/Shanghai")
        day_two_start = datetime(2026, 7, 27, 10, 0, tzinfo=tenant_tz).astimezone(UTC)
        day_two_end = datetime(2026, 7, 27, 11, 0, tzinfo=tenant_tz).astimezone(UTC)
        day_two_slot = TimeSlot.objects.create(
            tenant=self.tenant,
            location=self.location,
            resource=self.resource,
            start=day_two_start,
            end=day_two_end,
            capacity=2,
        )
        booking_create_for_test(
            tenant=self.tenant,
            time_slot=self.time_slot,
            service=self.service,
            customer=self.customer,
            idempotency_key="trend-day0",
        )
        booking_create_for_test(
            tenant=self.tenant,
            time_slot=day_two_slot,
            service=self.service,
            customer=self.customer,
            idempotency_key="trend-day1",
        )
        self._as_admin()
        response = self.client.get(
            "/api/v1/acme/dashboard/summary/",
            {"date": "2026-07-26"},
        )
        trend = api_data(response)["seven_day_trend"]
        self.assertEqual(len(trend), 7)
        self.assertEqual(trend[0]["date"], "2026-07-26")
        self.assertEqual(trend[0]["count"], 1)
        self.assertEqual(trend[1]["count"], 1)

    def test_dashboard_filters_by_location(self):
        """看板支持按地点筛选。"""
        other_customer = TenantCustomer.objects.create(
            tenant=self.tenant,
            user=User.objects.create_user(username="other-cust"),
        )
        booking_create_for_test(
            tenant=self.tenant,
            time_slot=self.time_slot,
            service=self.service,
            customer=self.customer,
            idempotency_key="loc-main",
        )
        booking_create_for_test(
            tenant=self.tenant,
            time_slot=self.other_slot,
            service=self.other_service,
            customer=other_customer,
            idempotency_key="loc-branch",
        )
        self._as_admin()
        response = self.client.get(
            "/api/v1/acme/dashboard/summary/",
            {"date": "2026-07-26", "location_id": self.location.id},
        )
        data = api_data(response)
        location_counts = {
            row["location_id"]: row["count"] for row in data["bookings_by_location"]
        }
        self.assertEqual(location_counts.get(self.location.id), 1)
        self.assertNotIn(self.other_location.id, location_counts)

    def test_dashboard_uses_short_cache(self):
        """看板聚合结果使用短缓存。"""
        booking_create_for_test(
            tenant=self.tenant,
            time_slot=self.time_slot,
            service=self.service,
            customer=self.customer,
            idempotency_key="cache-booking",
        )
        self._as_admin()
        first = self.client.get(
            "/api/v1/acme/dashboard/summary/",
            {"date": "2026-07-26"},
        )
        self.assertEqual(api_data(first)["today_summary"]["confirmed"], 1)

        Booking.objects.filter(tenant=self.tenant).delete()
        second = self.client.get(
            "/api/v1/acme/dashboard/summary/",
            {"date": "2026-07-26"},
        )
        self.assertEqual(api_data(second)["today_summary"]["confirmed"], 1)

        cache.clear()
        third = self.client.get(
            "/api/v1/acme/dashboard/summary/",
            {"date": "2026-07-26"},
        )
        self.assertEqual(api_data(third)["today_summary"]["confirmed"], 0)
