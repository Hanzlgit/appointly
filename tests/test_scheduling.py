from datetime import UTC, date, datetime, time, timedelta
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
        self.assertEqual(rule["slot_interval_minutes"], 30)
        self.assertEqual(rule["capacity"], 3)
        self.assertTrue(rule["is_active"])


class ScheduleRuleListTests(SchedulingAdminMixin, APITestCase):
    def test_list_rules_filters_by_resource_id(self):
        """验证列表 API 可按 resource_id 过滤。"""
        created = self._create_rule()
        other_resource = Resource.objects.create(
            tenant=self.tenant,
            location=self.location,
            name="Bob",
        )
        self._create_rule(resource_id=other_resource.id)

        response = self.client.get(
            "/api/v1/acme/scheduling/rules/",
            {"resource_id": self.resource.id},
        )

        self.assertEqual(response.status_code, 200)
        rules = api_data(response)["rules"]
        self.assertEqual(len(rules), 1)
        self.assertEqual(rules[0]["id"], created["id"])


class ScheduleRuleValidationTests(SchedulingAdminMixin, APITestCase):
    def test_create_rejects_window_not_divisible_by_interval(self):
        """验证营业窗口无法被间隔整除时拒绝创建。"""
        response = self.client.post(
            "/api/v1/acme/scheduling/rules/",
            {
                "location_id": self.location.id,
                "resource_id": self.resource.id,
                "days_of_week": [0],
                "start_time": "09:00",
                "end_time": "09:50",
                "slot_interval_minutes": 30,
                "capacity": 1,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("整除", api_message(response))

    def test_create_rejects_invalid_slot_interval(self):
        """验证非法时段间隔值返回 400。"""
        response = self.client.post(
            "/api/v1/acme/scheduling/rules/",
            {
                "location_id": self.location.id,
                "resource_id": self.resource.id,
                "days_of_week": [0],
                "start_time": "09:00",
                "end_time": "10:00",
                "slot_interval_minutes": 20,
                "capacity": 1,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)


class ScheduleRuleSlotSplitTests(SchedulingAdminMixin, APITestCase):
    def test_create_sync_generates_split_timeslots_for_window(self):
        """验证创建规则后同步按间隔切分并生成固定时段。"""
        rule_data = self._create_rule(
            days_of_week=[0],
            start_time="09:00",
            end_time="12:00",
            slot_interval_minutes=30,
        )
        rule = ScheduleRule.objects.get(id=rule_data["id"])

        tenant_tz = ZoneInfo("Asia/Shanghai")
        today_local = timezone.now().astimezone(tenant_tz).date()
        while today_local.weekday() != 0:
            today_local += timedelta(days=1)

        slots = TimeSlot.objects.filter(schedule_rule=rule, start__date=today_local)
        self.assertEqual(slots.count(), 6)
        first_start = datetime.combine(today_local, time(9, 0), tzinfo=tenant_tz).astimezone(UTC)
        self.assertTrue(slots.filter(start=first_start).exists())


class TimeSlotGenerationTests(SchedulingAdminMixin, APITestCase):
    def test_schedule_rule_generates_future_timeslots(self):
        """验证排班规则可批量生成未来固定时段。"""
        rule_data = self._create_rule(days_of_week=[0, 1, 2, 3, 4, 5, 6])
        rule = ScheduleRule.objects.get(id=rule_data["id"])

        tenant_tz = ZoneInfo("Asia/Shanghai")
        today_local = timezone.now().astimezone(tenant_tz).date()
        end_local = today_local + timedelta(days=6)
        slot_count = TimeSlot.objects.filter(
            schedule_rule=rule,
            start__date__gte=today_local,
            start__date__lte=end_local,
        ).count()

        self.assertEqual(slot_count, 14)
        created_count = scheduling_timeslots_generate_for_rule(
            tenant=self.tenant,
            rule=rule,
            from_date=today_local,
            to_date=end_local,
        )
        self.assertEqual(created_count, 0)
        self.assertEqual(
            TimeSlot.objects.filter(
                schedule_rule=rule,
                start__date__gte=today_local,
                start__date__lte=end_local,
            ).count(),
            14,
        )


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
        new_slot_end = datetime(2026, 8, 20, 10, 30, tzinfo=tenant_tz).astimezone(UTC)
        self.assertTrue(
            TimeSlot.objects.filter(
                schedule_rule=rule,
                start=new_slot_start,
                end=new_slot_end,
                status=TimeSlotStatus.OPEN,
            ).exists()
        )


class ScheduleRuleUpdateTests(SchedulingAdminMixin, APITestCase):
    def test_update_slot_interval_regenerates_split_timeslots(self):
        """验证更新时段间隔后从生效日按新间隔重新生成时段。"""
        rule_data = self._create_rule(
            days_of_week=[0],
            start_time="09:00",
            end_time="12:00",
            slot_interval_minutes=30,
        )
        rule = ScheduleRule.objects.get(id=rule_data["id"])

        effective_date = date(2026, 9, 7)
        while effective_date.weekday() != 0:
            effective_date += timedelta(days=1)

        response = self.client.patch(
            f"/api/v1/acme/scheduling/rules/{rule.id}/",
            {
                "effective_date": effective_date.isoformat(),
                "slot_interval_minutes": 15,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(api_data(response)["slot_interval_minutes"], 15)
        slots = TimeSlot.objects.filter(
            schedule_rule=rule,
            start__date=effective_date,
            status=TimeSlotStatus.OPEN,
        )
        self.assertEqual(slots.count(), 12)

    def test_update_rejects_window_not_divisible_by_interval(self):
        """验证更新时营业窗口无法被间隔整除则拒绝。"""
        rule_data = self._create_rule(
            start_time="09:00",
            end_time="10:00",
            slot_interval_minutes=30,
        )
        rule = ScheduleRule.objects.get(id=rule_data["id"])

        response = self.client.patch(
            f"/api/v1/acme/scheduling/rules/{rule.id}/",
            {
                "effective_date": date(2026, 9, 1).isoformat(),
                "end_time": "09:50",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("整除", api_message(response))

    def test_deactivate_closes_future_idle_slots_and_stops_generation(self):
        """验证停用规则后关闭未来空闲时段且不再生成新槽。"""
        rule_data = self._create_rule(days_of_week=[0, 1, 2, 3, 4, 5, 6])
        rule = ScheduleRule.objects.get(id=rule_data["id"])

        tenant_tz = ZoneInfo("Asia/Shanghai")
        today_local = timezone.now().astimezone(tenant_tz).date()
        future_slot_start = datetime.combine(today_local, time(9, 0), tzinfo=tenant_tz).astimezone(
            UTC
        )
        future_slot_end = datetime.combine(today_local, time(10, 0), tzinfo=tenant_tz).astimezone(
            UTC
        )
        future_slot = TimeSlot.objects.create(
            tenant=self.tenant,
            location=self.location,
            resource=self.resource,
            schedule_rule=rule,
            start=future_slot_start,
            end=future_slot_end,
            capacity=1,
            status=TimeSlotStatus.OPEN,
        )
        open_count_before = TimeSlot.objects.filter(
            schedule_rule=rule,
            status=TimeSlotStatus.OPEN,
            start__gte=future_slot_start,
        ).count()

        response = self.client.patch(
            f"/api/v1/acme/scheduling/rules/{rule.id}/",
            {
                "effective_date": today_local.isoformat(),
                "is_active": False,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(api_data(response)["is_active"])
        future_slot.refresh_from_db()
        self.assertEqual(future_slot.status, TimeSlotStatus.CLOSED)
        self.assertEqual(
            TimeSlot.objects.filter(
                schedule_rule=rule,
                status=TimeSlotStatus.OPEN,
                start__gte=future_slot_start,
            ).count(),
            0,
        )
        self.assertGreater(open_count_before, 0)

        created = scheduling_timeslots_generate_for_rule(
            tenant=self.tenant,
            rule=ScheduleRule.objects.get(id=rule.id),
            from_date=today_local,
        )
        self.assertEqual(created, 0)

    def test_reactivate_regenerates_slots_from_effective_date(self):
        """验证重新启用规则后从生效日重新生成时段。"""
        rule_data = self._create_rule(days_of_week=[0, 1, 2, 3, 4, 5, 6])
        rule = ScheduleRule.objects.get(id=rule_data["id"])

        tenant_tz = ZoneInfo("Asia/Shanghai")
        today_local = timezone.now().astimezone(tenant_tz).date()

        deactivate_response = self.client.patch(
            f"/api/v1/acme/scheduling/rules/{rule.id}/",
            {
                "effective_date": today_local.isoformat(),
                "is_active": False,
            },
            format="json",
        )
        self.assertEqual(deactivate_response.status_code, 200)

        activate_response = self.client.patch(
            f"/api/v1/acme/scheduling/rules/{rule.id}/",
            {
                "effective_date": today_local.isoformat(),
                "is_active": True,
            },
            format="json",
        )

        self.assertEqual(activate_response.status_code, 200)
        self.assertTrue(api_data(activate_response)["is_active"])
        self.assertGreater(
            TimeSlot.objects.filter(
                schedule_rule=rule,
                status=TimeSlotStatus.OPEN,
                start__date__gte=today_local,
            ).count(),
            0,
        )


class SchedulingCeleryTaskTests(SchedulingAdminMixin, APITestCase):
    def test_celery_task_generates_timeslots_for_active_rules(self):
        """验证 Celery 任务可为活跃规则批量生成时段且幂等。"""
        self._create_rule(days_of_week=[0, 1, 2, 3, 4, 5, 6])

        initial_count = TimeSlot.objects.filter(tenant=self.tenant).count()
        self.assertGreater(initial_count, 0)

        created_total = scheduling_generate_timeslots_for_all_tenants()
        self.assertEqual(created_total, 0)
        self.assertEqual(TimeSlot.objects.filter(tenant=self.tenant).count(), initial_count)

        created_again = scheduling_generate_timeslots_for_all_tenants()
        self.assertEqual(created_again, 0)
        self.assertEqual(TimeSlot.objects.filter(tenant=self.tenant).count(), initial_count)
