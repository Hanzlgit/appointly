from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from catalog.models import Location, Resource
from django.contrib.auth.models import User
from django.utils import timezone
from rest_framework.test import APITestCase
from scheduling.models import BookingStatus, ScheduleRule, TimeSlot, TimeSlotStatus
from scheduling.services.time_slot import scheduling_timeslots_generate_for_rule
from scheduling.tasks import scheduling_generate_timeslots_for_all_tenants
from tenants.models import Tenant, TenantMembership, TenantRole

from tests.support import api_data, api_message, booking_create_for_test


class SchedulingAdminMixin:
    """为 scheduling 管理端 API 测试提供租户管理员 JWT 与目录数据。"""

    tenant: Tenant
    admin: User
    location: Location
    resource: Resource

    def setUp(self):
        """准备租户、管理员、地点、资源与 Bearer 凭据。"""
        self.tenant = Tenant.objects.create(slug="acme", name="Acme Corp", timezone="Asia/Shanghai")
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

        login_response = self.client.post(
            "/api/v1/auth/staff/sessions/",
            {"login": "tenant-admin", "password": "StrongPass123!"},
            format="json",
        )
        access = api_data(login_response)["access"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")

    def _create_rule(self, **overrides) -> dict:
        """通过 API 创建排班规则并返回响应 data。

        Args:
            **overrides: 覆盖默认请求字段。

        Returns:
            dict: 创建成功的规则响应 data。
        """
        payload = {
            "location_id": self.location.id,
            "resource_id": self.resource.id,
            "days_of_week": [0, 2, 4],
            "start_time": "09:00",
            "end_time": "10:00",
            "capacity": 3,
        }
        payload.update(overrides)
        response = self.client.post(
            "/api/v1/acme/scheduling/rules/",
            payload,
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        return api_data(response)


class ScheduleRuleCreateTests(SchedulingAdminMixin, APITestCase):
    def test_tenant_admin_can_create_schedule_rule(self):
        """验证租户管理员可创建周期排班规则。"""
        rule = self._create_rule()

        self.assertEqual(rule["location_id"], self.location.id)
        self.assertEqual(rule["resource_id"], self.resource.id)
        self.assertEqual(rule["days_of_week"], [0, 2, 4])
        self.assertEqual(rule["start_time"], "09:00:00")
        self.assertEqual(rule["end_time"], "10:00:00")
        self.assertEqual(rule["capacity"], 3)
        self.assertTrue(rule["is_active"])


class TimeSlotGenerationTests(SchedulingAdminMixin, APITestCase):
    def test_schedule_rule_generates_future_timeslots(self):
        """验证排班规则可批量生成未来固定时段。"""
        rule_data = self._create_rule(days_of_week=[0, 1, 2, 3, 4, 5, 6])
        rule = ScheduleRule.objects.get(id=rule_data["id"])

        tenant_tz = ZoneInfo("Asia/Shanghai")
        today_local = timezone.now().astimezone(tenant_tz).date()
        created_count = scheduling_timeslots_generate_for_rule(
            tenant=self.tenant,
            rule=rule,
            from_date=today_local,
            to_date=today_local + timedelta(days=6),
        )

        self.assertEqual(created_count, 7)
        self.assertEqual(TimeSlot.objects.filter(schedule_rule=rule).count(), 7)


class TimeSlotOverlapTests(SchedulingAdminMixin, APITestCase):
    def test_overlapping_timeslot_for_same_resource_is_rejected(self):
        """验证同一资源重叠时段创建被拒绝。"""
        tenant_tz = ZoneInfo("Asia/Shanghai")
        slot_start = datetime(2026, 7, 27, 9, 0, tzinfo=tenant_tz).astimezone(UTC)
        slot_end = datetime(2026, 7, 27, 10, 0, tzinfo=tenant_tz).astimezone(UTC)

        first_response = self.client.post(
            "/api/v1/acme/scheduling/time-slots/",
            {
                "location_id": self.location.id,
                "resource_id": self.resource.id,
                "start": slot_start.isoformat(),
                "end": slot_end.isoformat(),
                "capacity": 1,
            },
            format="json",
        )
        self.assertEqual(first_response.status_code, 201)

        overlap_response = self.client.post(
            "/api/v1/acme/scheduling/time-slots/",
            {
                "location_id": self.location.id,
                "resource_id": self.resource.id,
                "start": (slot_start + timedelta(minutes=30)).isoformat(),
                "end": (slot_end + timedelta(minutes=30)).isoformat(),
                "capacity": 1,
            },
            format="json",
        )
        self.assertEqual(overlap_response.status_code, 400)
        self.assertIn("重叠", api_message(overlap_response))


class TimeSlotManualCloseTests(SchedulingAdminMixin, APITestCase):
    def test_admin_can_manually_create_and_close_idle_timeslot(self):
        """验证管理员可手工补充并关闭空闲时段。"""
        tenant_tz = ZoneInfo("Asia/Shanghai")
        slot_start = datetime(2026, 8, 1, 14, 0, tzinfo=tenant_tz).astimezone(UTC)
        slot_end = datetime(2026, 8, 1, 15, 0, tzinfo=tenant_tz).astimezone(UTC)

        create_response = self.client.post(
            "/api/v1/acme/scheduling/time-slots/",
            {
                "location_id": self.location.id,
                "resource_id": self.resource.id,
                "start": slot_start.isoformat(),
                "end": slot_end.isoformat(),
                "capacity": 2,
            },
            format="json",
        )
        self.assertEqual(create_response.status_code, 201)
        time_slot_id = api_data(create_response)["id"]

        close_response = self.client.post(
            f"/api/v1/acme/scheduling/time-slots/{time_slot_id}/close/",
            {},
            format="json",
        )
        self.assertEqual(close_response.status_code, 200)
        self.assertEqual(api_data(close_response)["status"], TimeSlotStatus.CLOSED)


class TimeSlotBatchCloseTests(SchedulingAdminMixin, APITestCase):
    def _create_open_slot(self, *, slot_start: datetime, slot_end: datetime) -> TimeSlot:
        """创建开放时段测试数据。

        Args:
            slot_start (datetime): 开始时间。
            slot_end (datetime): 结束时间。

        Returns:
            TimeSlot: 新创建的开放时段。
        """
        return TimeSlot.objects.create(
            tenant=self.tenant,
            location=self.location,
            resource=self.resource,
            start=slot_start,
            end=slot_end,
            capacity=1,
            status=TimeSlotStatus.OPEN,
        )

    def test_batch_close_rejects_when_active_bookings_exist(self):
        """验证批量关闭时存在有效预约则拒绝并返回冲突列表。"""
        tenant_tz = ZoneInfo("Asia/Shanghai")
        slot_start = datetime(2026, 8, 10, 9, 0, tzinfo=tenant_tz).astimezone(UTC)
        slot_end = datetime(2026, 8, 10, 10, 0, tzinfo=tenant_tz).astimezone(UTC)
        time_slot = self._create_open_slot(slot_start=slot_start, slot_end=slot_end)
        booking = booking_create_for_test(
            tenant=self.tenant,
            time_slot=time_slot,
            idempotency_key="batch-close-conflict",
        )

        response = self.client.post(
            "/api/v1/acme/scheduling/time-slots/batch-close/",
            {
                "start": slot_start.isoformat(),
                "end": slot_end.isoformat(),
                "resource_id": self.resource.id,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(api_data(response)["conflicts"], [booking.id])
        time_slot.refresh_from_db()
        self.assertEqual(time_slot.status, TimeSlotStatus.OPEN)

    def test_batch_close_succeeds_when_no_active_bookings(self):
        """验证无有效预约时可批量关闭时段。"""
        tenant_tz = ZoneInfo("Asia/Shanghai")
        slot_start = datetime(2026, 8, 11, 9, 0, tzinfo=tenant_tz).astimezone(UTC)
        slot_end = datetime(2026, 8, 11, 10, 0, tzinfo=tenant_tz).astimezone(UTC)
        self._create_open_slot(slot_start=slot_start, slot_end=slot_end)

        response = self.client.post(
            "/api/v1/acme/scheduling/time-slots/batch-close/",
            {
                "start": slot_start.isoformat(),
                "end": slot_end.isoformat(),
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(api_data(response)["closed_count"], 1)


class ScheduleRuleEffectiveDateTests(SchedulingAdminMixin, APITestCase):
    def test_rule_change_rejects_when_active_bookings_on_or_after_effective_date(self):
        """验证规则变更时生效日及之后有有效预约则拒绝。"""
        rule_data = self._create_rule()
        rule = ScheduleRule.objects.get(id=rule_data["id"])

        tenant_tz = ZoneInfo("Asia/Shanghai")
        effective_date = date(2026, 8, 15)
        slot_start = datetime(2026, 8, 15, 9, 0, tzinfo=tenant_tz).astimezone(UTC)
        slot_end = datetime(2026, 8, 15, 10, 0, tzinfo=tenant_tz).astimezone(UTC)
        time_slot = TimeSlot.objects.create(
            tenant=self.tenant,
            location=self.location,
            resource=self.resource,
            schedule_rule=rule,
            start=slot_start,
            end=slot_end,
            capacity=1,
            status=TimeSlotStatus.OPEN,
        )
        booking_create_for_test(
            tenant=self.tenant,
            time_slot=time_slot,
            status=BookingStatus.PENDING,
            idempotency_key="rule-change-conflict",
        )

        response = self.client.patch(
            f"/api/v1/acme/scheduling/rules/{rule.id}/",
            {
                "effective_date": effective_date.isoformat(),
                "start_time": "10:00",
                "end_time": "11:00",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("有效预约", api_message(response))

    def test_rule_change_closes_old_idle_slots_and_regenerates_from_effective_date(self):
        """验证规则变更通过后关闭旧空闲时段并从生效日重新生成。"""
        rule_data = self._create_rule(days_of_week=[0, 1, 2, 3, 4, 5, 6])
        rule = ScheduleRule.objects.get(id=rule_data["id"])

        tenant_tz = ZoneInfo("Asia/Shanghai")
        effective_date = date(2026, 8, 20)
        old_slot_start = datetime(2026, 8, 20, 9, 0, tzinfo=tenant_tz).astimezone(UTC)
        old_slot_end = datetime(2026, 8, 20, 10, 0, tzinfo=tenant_tz).astimezone(UTC)
        old_slot = TimeSlot.objects.create(
            tenant=self.tenant,
            location=self.location,
            resource=self.resource,
            schedule_rule=rule,
            start=old_slot_start,
            end=old_slot_end,
            capacity=3,
            status=TimeSlotStatus.OPEN,
        )

        response = self.client.patch(
            f"/api/v1/acme/scheduling/rules/{rule.id}/",
            {
                "effective_date": effective_date.isoformat(),
                "start_time": "10:00",
                "end_time": "11:00",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(api_data(response)["start_time"], "10:00:00")

        old_slot.refresh_from_db()
        self.assertEqual(old_slot.status, TimeSlotStatus.CLOSED)

        new_slot_start = datetime(2026, 8, 20, 10, 0, tzinfo=tenant_tz).astimezone(UTC)
        new_slot_end = datetime(2026, 8, 20, 11, 0, tzinfo=tenant_tz).astimezone(UTC)
        self.assertTrue(
            TimeSlot.objects.filter(
                schedule_rule=rule,
                start=new_slot_start,
                end=new_slot_end,
                status=TimeSlotStatus.OPEN,
            ).exists()
        )


class SchedulingCeleryTaskTests(SchedulingAdminMixin, APITestCase):
    def test_celery_task_generates_timeslots_for_active_rules(self):
        """验证 Celery 任务可为活跃规则批量生成时段且幂等。"""
        self._create_rule(days_of_week=[0, 1, 2, 3, 4, 5, 6])

        created_total = scheduling_generate_timeslots_for_all_tenants()
        self.assertGreater(created_total, 0)
        initial_count = TimeSlot.objects.filter(tenant=self.tenant).count()

        created_again = scheduling_generate_timeslots_for_all_tenants()
        self.assertEqual(created_again, 0)
        self.assertEqual(TimeSlot.objects.filter(tenant=self.tenant).count(), initial_count)
