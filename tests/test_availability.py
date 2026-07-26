from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from catalog.models import Location, Resource, Service
from django.core.cache import cache
from django.db import connection
from django.test import override_settings
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APITestCase
from scheduling.models import TimeSlot, TimeSlotStatus
from tenants.models import Tenant

from tests.support import api_data, booking_create_for_test


@override_settings(
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "availability-tests",
        }
    },
)
class AvailabilityQueryTests(APITestCase):
    """可用时段查询 API 测试。"""

    tenant: Tenant
    location: Location
    resource: Resource
    service: Service

    def setUp(self):
        """准备租户、目录与时段测试数据。"""
        cache.clear()
        self.tenant = Tenant.objects.create(
            slug="acme",
            name="Acme Corp",
            timezone="Asia/Shanghai",
        )
        self.location = Location.objects.create(tenant=self.tenant, name="Main Studio")
        self.resource = Resource.objects.create(
            tenant=self.tenant,
            name="Alice",
            resource_type="staff",
        )
        self.location.resources.add(self.resource)
        self.service = Service.objects.create(
            tenant=self.tenant,
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
            capacity=3,
            status=TimeSlotStatus.OPEN,
        )

    def _query_availability(self, **params):
        """调用可用时段查询 API。

        Args:
            **params: 查询参数字典。

        Returns:
            Response: DRF 测试客户端响应。
        """
        query = {
            "start": params.pop("start", self.slot_start.isoformat()),
            "end": params.pop("end", self.slot_end.isoformat()),
        }
        query.update(params)
        return self.client.get("/api/v1/acme/scheduling/availability/", query)

    def test_resource_query_returns_open_slots_with_remaining_capacity(self):
        """指定资源时返回可用时段及剩余容量。"""
        booking_create_for_test(
            tenant=self.tenant,
            time_slot=self.time_slot,
            service=self.service,
            party_size=1,
            idempotency_key="avail-seed-1",
        )

        response = self._query_availability(resource_id=self.resource.id)

        self.assertEqual(response.status_code, 200)
        payload = api_data(response)
        self.assertEqual(len(payload["slots"]), 1)
        slot = payload["slots"][0]
        self.assertEqual(slot["time_slot_id"], self.time_slot.id)
        self.assertEqual(slot["resource_id"], self.resource.id)
        self.assertEqual(slot["location_id"], self.location.id)
        self.assertEqual(slot["capacity"], 3)
        self.assertEqual(slot["remaining_capacity"], 2)
        self.assertEqual(slot["start"], "2026-08-01T09:00:00+08:00")
        self.assertEqual(slot["end"], "2026-08-01T10:00:00+08:00")

    def test_aggregate_query_sums_remaining_capacity_by_service_location_time(self):
        """未指定资源时按服务、地点与时间聚合剩余容量。"""
        other_resource = Resource.objects.create(
            tenant=self.tenant,
            name="Bob",
            resource_type="staff",
        )
        self.location.resources.add(other_resource)
        self.service.resources.add(other_resource)
        TimeSlot.objects.create(
            tenant=self.tenant,
            location=self.location,
            resource=other_resource,
            start=self.slot_start,
            end=self.slot_end,
            capacity=2,
            status=TimeSlotStatus.OPEN,
        )

        response = self._query_availability(service_id=self.service.id)

        self.assertEqual(response.status_code, 200)
        payload = api_data(response)
        self.assertEqual(payload["mode"], "aggregate")
        self.assertEqual(len(payload["availability"]), 1)
        item = payload["availability"][0]
        self.assertEqual(item["service_id"], self.service.id)
        self.assertEqual(item["location_id"], self.location.id)
        self.assertEqual(item["remaining_capacity"], 5)
        self.assertEqual(item["start"], "2026-08-01T09:00:00+08:00")
        self.assertEqual(item["end"], "2026-08-01T10:00:00+08:00")

    def test_repeated_query_uses_cache_on_second_request(self):
        """相同查询第二次命中缓存，不再访问排班表。"""
        first = self._query_availability(resource_id=self.resource.id)
        self.assertEqual(first.status_code, 200)

        with CaptureQueriesContext(connection) as context:
            second = self._query_availability(resource_id=self.resource.id)
        self.assertEqual(second.status_code, 200)
        scheduling_queries = [
            query for query in context.captured_queries if "scheduling_" in query["sql"]
        ]
        self.assertEqual(scheduling_queries, [])
        self.assertEqual(api_data(first), api_data(second))

    def test_booking_create_invalidates_availability_cache(self):
        """创建预约后可用容量立即反映最新 MySQL 数据。"""
        first = self._query_availability(resource_id=self.resource.id)
        self.assertEqual(api_data(first)["slots"][0]["remaining_capacity"], 3)

        booking_create_for_test(
            tenant=self.tenant,
            time_slot=self.time_slot,
            service=self.service,
            party_size=2,
            idempotency_key="avail-cache-test",
        )

        second = self._query_availability(resource_id=self.resource.id)
        self.assertEqual(api_data(second)["slots"][0]["remaining_capacity"], 1)
