from catalog.models import CatalogBusinessReference, Location, Resource, Service
from django.contrib.auth.models import User
from rest_framework.test import APITestCase
from tenants.models import Tenant, TenantMembership, TenantRole

from tests.support import api_data, api_message


class CatalogAdminMixin:
    """为 catalog 管理端 API 测试提供租户管理员 JWT。"""

    tenant: Tenant
    admin: User

    def setUp(self):
        """准备租户、管理员与 Bearer 凭据。"""
        self.tenant = Tenant.objects.create(slug="acme", name="Acme Corp")
        self.admin = User.objects.create_user(username="tenant-admin", password="StrongPass123!")
        TenantMembership.objects.create(
            tenant=self.tenant,
            user=self.admin,
            role=TenantRole.TENANT_ADMIN,
        )
        login_response = self.client.post(
            "/api/v1/auth/staff/sessions/",
            {"login": "tenant-admin", "password": "StrongPass123!"},
            format="json",
        )
        access = api_data(login_response)["access"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")


class CatalogLocationCreateTests(CatalogAdminMixin, APITestCase):
    def test_tenant_admin_can_create_location(self):
        """验证租户管理员可创建服务地点。"""
        response = self.client.post(
            "/api/v1/acme/catalog/locations/",
            {"name": "Downtown Studio", "address": "123 Main St"},
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        location = api_data(response)
        self.assertEqual(location["name"], "Downtown Studio")
        self.assertEqual(location["address"], "123 Main St")
        self.assertTrue(location["is_active"])
        self.assertEqual(location["resource_count"], 0)
        self.assertEqual(location["service_count"], 0)


class CatalogLocationListTests(CatalogAdminMixin, APITestCase):
    def test_tenant_admin_can_list_locations_with_resource_and_service_count(self):
        """验证地点列表返回 resource_count 与 service_count。"""
        location = Location.objects.create(tenant=self.tenant, name="North Branch")
        Resource.objects.create(tenant=self.tenant, location=location, name="Room A")
        Resource.objects.create(tenant=self.tenant, location=location, name="Room B")
        Service.objects.create(
            tenant=self.tenant,
            location=location,
            name="Haircut",
            duration_minutes=30,
        )

        response = self.client.get("/api/v1/acme/catalog/locations/")

        self.assertEqual(response.status_code, 200)
        locations = api_data(response)["locations"]
        self.assertEqual(len(locations), 1)
        self.assertEqual(locations[0]["name"], "North Branch")
        self.assertEqual(locations[0]["resource_count"], 2)
        self.assertEqual(locations[0]["service_count"], 1)


class CatalogLocationUpdateTests(CatalogAdminMixin, APITestCase):
    def test_tenant_admin_can_update_location(self):
        """验证租户管理员可更新服务地点。"""
        create_response = self.client.post(
            "/api/v1/acme/catalog/locations/",
            {"name": "Old Name"},
            format="json",
        )
        location_id = api_data(create_response)["id"]

        response = self.client.patch(
            f"/api/v1/acme/catalog/locations/{location_id}/",
            {"name": "New Name", "address": "Updated Address"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        updated = api_data(response)
        self.assertEqual(updated["name"], "New Name")
        self.assertEqual(updated["address"], "Updated Address")


class CatalogLocationDeleteTests(CatalogAdminMixin, APITestCase):
    def test_tenant_admin_can_delete_unreferenced_location(self):
        """验证租户管理员可物理删除未被引用的地点。"""
        create_response = self.client.post(
            "/api/v1/acme/catalog/locations/",
            {"name": "Temp Location"},
            format="json",
        )
        location_id = api_data(create_response)["id"]

        response = self.client.delete(f"/api/v1/acme/catalog/locations/{location_id}/")

        self.assertEqual(response.status_code, 204)
        self.assertFalse(Location.objects.filter(id=location_id).exists())

    def test_referenced_location_cannot_be_deleted_but_can_be_deactivated(self):
        """验证被引用的地点不能物理删除，但可以停用。"""
        create_response = self.client.post(
            "/api/v1/acme/catalog/locations/",
            {"name": "Referenced Location"},
            format="json",
        )
        location_id = api_data(create_response)["id"]
        CatalogBusinessReference.objects.create(tenant=self.tenant, location_id=location_id)

        delete_response = self.client.delete(f"/api/v1/acme/catalog/locations/{location_id}/")
        self.assertEqual(delete_response.status_code, 400)
        self.assertEqual(api_message(delete_response), "该地点已被业务引用，只能停用。")
        self.assertTrue(Location.objects.filter(id=location_id).exists())

        patch_response = self.client.patch(
            f"/api/v1/acme/catalog/locations/{location_id}/",
            {"is_active": False},
            format="json",
        )
        self.assertEqual(patch_response.status_code, 200)
        self.assertFalse(api_data(patch_response)["is_active"])


class CatalogLocationServiceTests(CatalogAdminMixin, APITestCase):
    def setUp(self):
        """准备租户、管理员、两个地点。"""
        super().setUp()
        self.location_a = Location.objects.create(tenant=self.tenant, name="Branch A")
        self.location_b = Location.objects.create(tenant=self.tenant, name="Branch B")

    def test_tenant_admin_can_create_service_under_location(self):
        """验证可在地点下创建服务，响应含 location_id。"""
        response = self.client.post(
            f"/api/v1/acme/catalog/locations/{self.location_a.id}/services/",
            {
                "name": "Haircut",
                "description": "Standard cut",
                "duration_minutes": 30,
                "price_cents": 5000,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        service = api_data(response)
        self.assertEqual(service["name"], "Haircut")
        self.assertEqual(service["duration_minutes"], 30)
        self.assertEqual(service["price_cents"], 5000)
        self.assertEqual(service["location_id"], self.location_a.id)
        self.assertEqual(service["resource_ids"], [])

    def test_tenant_admin_can_list_update_and_delete_location_services(self):
        """验证地点下服务 CRUD 闭环。"""
        create_response = self.client.post(
            f"/api/v1/acme/catalog/locations/{self.location_a.id}/services/",
            {
                "name": "Consultation",
                "duration_minutes": 60,
            },
            format="json",
        )
        service_id = api_data(create_response)["id"]

        list_response = self.client.get(
            f"/api/v1/acme/catalog/locations/{self.location_a.id}/services/",
        )
        self.assertEqual(list_response.status_code, 200)
        services = api_data(list_response)["services"]
        self.assertEqual(len(services), 1)
        self.assertEqual(services[0]["name"], "Consultation")

        patch_response = self.client.patch(
            f"/api/v1/acme/catalog/locations/{self.location_a.id}/services/{service_id}/",
            {"name": "Consultation Updated", "is_active": False},
            format="json",
        )
        self.assertEqual(patch_response.status_code, 200)
        updated = api_data(patch_response)
        self.assertEqual(updated["name"], "Consultation Updated")
        self.assertFalse(updated["is_active"])

        delete_response = self.client.delete(
            f"/api/v1/acme/catalog/locations/{self.location_a.id}/services/{service_id}/",
        )
        self.assertEqual(delete_response.status_code, 204)
        self.assertFalse(Service.objects.filter(id=service_id).exists())

    def test_service_can_link_same_location_resources(self):
        """验证服务可关联同地点资源。"""
        resource = Resource.objects.create(
            tenant=self.tenant,
            location=self.location_a,
            name="Room A",
        )

        service_response = self.client.post(
            f"/api/v1/acme/catalog/locations/{self.location_a.id}/services/",
            {
                "name": "Consultation",
                "duration_minutes": 60,
                "resource_ids": [resource.id],
            },
            format="json",
        )
        self.assertEqual(service_response.status_code, 201)
        self.assertEqual(api_data(service_response)["resource_ids"], [resource.id])

    def test_cross_location_resource_link_rejected(self):
        """验证跨地点关联资源返回 400。"""
        resource_b = Resource.objects.create(
            tenant=self.tenant,
            location=self.location_b,
            name="Room B",
        )

        response = self.client.post(
            f"/api/v1/acme/catalog/locations/{self.location_a.id}/services/",
            {
                "name": "Consultation",
                "duration_minutes": 60,
                "resource_ids": [resource_b.id],
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(api_message(response), "关联资源必须属于同一地点。")

    def test_same_name_allowed_across_locations(self):
        """验证不同地点下允许同名服务。"""
        response_a = self.client.post(
            f"/api/v1/acme/catalog/locations/{self.location_a.id}/services/",
            {"name": "Haircut", "duration_minutes": 30},
            format="json",
        )
        response_b = self.client.post(
            f"/api/v1/acme/catalog/locations/{self.location_b.id}/services/",
            {"name": "Haircut", "duration_minutes": 45},
            format="json",
        )

        self.assertEqual(response_a.status_code, 201)
        self.assertEqual(response_b.status_code, 201)

    def test_duplicate_name_within_same_location_rejected(self):
        """验证同地点下同名服务冲突。"""
        self.client.post(
            f"/api/v1/acme/catalog/locations/{self.location_a.id}/services/",
            {"name": "Haircut", "duration_minutes": 30},
            format="json",
        )

        response = self.client.post(
            f"/api/v1/acme/catalog/locations/{self.location_a.id}/services/",
            {"name": "Haircut", "duration_minutes": 45},
            format="json",
        )

        self.assertEqual(response.status_code, 400)

    def test_service_not_accessible_under_wrong_location(self):
        """验证服务不能通过错误地点 URL 访问。"""
        create_response = self.client.post(
            f"/api/v1/acme/catalog/locations/{self.location_a.id}/services/",
            {"name": "Haircut", "duration_minutes": 30},
            format="json",
        )
        service_id = api_data(create_response)["id"]

        response = self.client.get(
            f"/api/v1/acme/catalog/locations/{self.location_b.id}/services/{service_id}/",
        )
        self.assertEqual(response.status_code, 404)

    def test_global_services_endpoint_removed(self):
        """验证租户级全局服务端点已移除。"""
        response = self.client.get("/api/v1/acme/catalog/services/")
        self.assertEqual(response.status_code, 404)


class CatalogLocationResourceTests(CatalogAdminMixin, APITestCase):
    def setUp(self):
        """准备租户、管理员、两个地点。"""
        super().setUp()
        self.location_a = Location.objects.create(tenant=self.tenant, name="Branch A")
        self.location_b = Location.objects.create(tenant=self.tenant, name="Branch B")

    def test_tenant_admin_can_create_resource_under_location(self):
        """验证可在地点下创建资源，响应含 location_id。"""
        response = self.client.post(
            f"/api/v1/acme/catalog/locations/{self.location_a.id}/resources/",
            {"name": "Alice"},
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        resource = api_data(response)
        self.assertEqual(resource["name"], "Alice")
        self.assertEqual(resource["location_id"], self.location_a.id)
        self.assertTrue(resource["is_active"])
        self.assertNotIn("resource_type", resource)
        self.assertNotIn("staff_user_id", resource)
        self.assertNotIn("location_ids", resource)

    def test_tenant_admin_can_list_update_and_delete_location_resources(self):
        """验证地点下资源 CRUD 闭环。"""
        create_response = self.client.post(
            f"/api/v1/acme/catalog/locations/{self.location_a.id}/resources/",
            {"name": "Room A"},
            format="json",
        )
        resource_id = api_data(create_response)["id"]

        list_response = self.client.get(
            f"/api/v1/acme/catalog/locations/{self.location_a.id}/resources/",
        )
        self.assertEqual(list_response.status_code, 200)
        resources = api_data(list_response)["resources"]
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["name"], "Room A")

        patch_response = self.client.patch(
            f"/api/v1/acme/catalog/locations/{self.location_a.id}/resources/{resource_id}/",
            {"name": "Room A Updated", "is_active": False},
            format="json",
        )
        self.assertEqual(patch_response.status_code, 200)
        updated = api_data(patch_response)
        self.assertEqual(updated["name"], "Room A Updated")
        self.assertFalse(updated["is_active"])

        delete_response = self.client.delete(
            f"/api/v1/acme/catalog/locations/{self.location_a.id}/resources/{resource_id}/",
        )
        self.assertEqual(delete_response.status_code, 204)
        self.assertFalse(Resource.objects.filter(id=resource_id).exists())

    def test_same_name_allowed_across_locations(self):
        """验证不同地点下允许同名资源。"""
        response_a = self.client.post(
            f"/api/v1/acme/catalog/locations/{self.location_a.id}/resources/",
            {"name": "Alice"},
            format="json",
        )
        response_b = self.client.post(
            f"/api/v1/acme/catalog/locations/{self.location_b.id}/resources/",
            {"name": "Alice"},
            format="json",
        )

        self.assertEqual(response_a.status_code, 201)
        self.assertEqual(response_b.status_code, 201)

    def test_duplicate_name_within_same_location_rejected(self):
        """验证同地点下同名资源冲突。"""
        self.client.post(
            f"/api/v1/acme/catalog/locations/{self.location_a.id}/resources/",
            {"name": "Alice"},
            format="json",
        )

        response = self.client.post(
            f"/api/v1/acme/catalog/locations/{self.location_a.id}/resources/",
            {"name": "Alice"},
            format="json",
        )

        self.assertEqual(response.status_code, 400)

    def test_resource_not_accessible_under_wrong_location(self):
        """验证资源不能通过错误地点 URL 访问。"""
        create_response = self.client.post(
            f"/api/v1/acme/catalog/locations/{self.location_a.id}/resources/",
            {"name": "Alice"},
            format="json",
        )
        resource_id = api_data(create_response)["id"]

        response = self.client.get(
            f"/api/v1/acme/catalog/locations/{self.location_b.id}/resources/{resource_id}/",
        )
        self.assertEqual(response.status_code, 404)

    def test_global_resources_endpoint_removed(self):
        """验证租户级全局资源端点已移除。"""
        response = self.client.get("/api/v1/acme/catalog/resources/")
        self.assertEqual(response.status_code, 404)


class CatalogPublicBrowseTests(APITestCase):
    def setUp(self):
        """准备租户与目录数据。"""
        self.tenant = Tenant.objects.create(slug="acme", name="Acme Corp")
        self.active_location = Location.objects.create(
            tenant=self.tenant,
            name="Open Branch",
            is_active=True,
        )
        Location.objects.create(tenant=self.tenant, name="Closed Branch", is_active=False)
        Service.objects.create(
            tenant=self.tenant,
            location=self.active_location,
            name="Active Service",
            duration_minutes=30,
            is_active=True,
        )
        Service.objects.create(
            tenant=self.tenant,
            location=self.active_location,
            name="Inactive Service",
            duration_minutes=45,
            is_active=False,
        )

    def test_unauthenticated_user_can_browse_active_catalog(self):
        """验证未认证用户可浏览活跃地点与服务。"""
        response = self.client.get("/api/v1/acme/catalog/public/")

        self.assertEqual(response.status_code, 200)
        catalog = api_data(response)
        self.assertEqual(len(catalog["locations"]), 1)
        self.assertEqual(catalog["locations"][0]["name"], "Open Branch")
        self.assertEqual(len(catalog["services"]), 1)
        self.assertEqual(catalog["services"][0]["name"], "Active Service")
        self.assertEqual(catalog["services"][0]["location_ids"], [])

    def test_public_service_includes_location_ids_from_linked_resources(self):
        """验证公开服务返回其资源所属地点列表。"""
        resource = Resource.objects.create(
            tenant=self.tenant,
            location=self.active_location,
            name="Alice",
            is_active=True,
        )
        service = Service.objects.get(tenant=self.tenant, name="Active Service")
        service.resources.add(resource)

        response = self.client.get("/api/v1/acme/catalog/public/")

        self.assertEqual(response.status_code, 200)
        services = api_data(response)["services"]
        self.assertEqual(services[0]["location_ids"], [self.active_location.id])


class CatalogTenantIsolationTests(APITestCase):
    def setUp(self):
        """准备两个租户及其管理员。"""
        self.tenant_a = Tenant.objects.create(slug="tenant-a", name="Tenant A")
        self.tenant_b = Tenant.objects.create(slug="tenant-b", name="Tenant B")
        self.admin_a = User.objects.create_user(username="admin-a", password="StrongPass123!")
        TenantMembership.objects.create(
            tenant=self.tenant_a,
            user=self.admin_a,
            role=TenantRole.TENANT_ADMIN,
        )
        self.location_a = Location.objects.create(tenant=self.tenant_a, name="A Location")
        self.location_b = Location.objects.create(tenant=self.tenant_b, name="B Location")
        login_response = self.client.post(
            "/api/v1/auth/staff/sessions/",
            {"login": "admin-a", "password": "StrongPass123!"},
            format="json",
        )
        access = api_data(login_response)["access"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")

    def test_tenant_admin_cannot_access_other_tenant_catalog(self):
        """验证租户管理员无法访问其他租户 catalog。"""
        response = self.client.get("/api/v1/tenant-b/catalog/locations/")

        self.assertEqual(response.status_code, 403)
        self.assertEqual(api_message(response), "无权访问该租户。")

    def test_tenant_admin_only_sees_own_locations(self):
        """验证租户管理员只能看到所属租户地点。"""
        Location.objects.create(tenant=self.tenant_b, name="Extra B Location")

        response = self.client.get("/api/v1/tenant-a/catalog/locations/")

        self.assertEqual(response.status_code, 200)
        locations = api_data(response)["locations"]
        self.assertEqual(len(locations), 1)
        self.assertEqual(locations[0]["name"], "A Location")

    def test_tenant_admin_cannot_access_other_tenant_nested_resources(self):
        """验证租户管理员无法访问其他租户地点下嵌套资源端点。"""
        response = self.client.get(
            f"/api/v1/tenant-b/catalog/locations/{self.location_b.id}/resources/",
        )
        self.assertEqual(response.status_code, 403)


class CatalogTimezoneTests(CatalogAdminMixin, APITestCase):
    def test_tenant_admin_can_update_timezone(self):
        """验证租户管理员可更新租户时区。"""
        response = self.client.patch(
            "/api/v1/acme/settings/",
            {"timezone": "America/New_York"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(api_data(response)["timezone"], "America/New_York")

    def test_api_datetimes_use_iso8601_with_timezone(self):
        """验证 API 时间字段使用带时区的 ISO 8601 格式。"""
        response = self.client.post(
            "/api/v1/acme/catalog/locations/",
            {"name": "Time Check"},
            format="json",
        )

        created_at = api_data(response)["created_at"]
        self.assertTrue(created_at.endswith("Z") or "+" in created_at or "-" in created_at[10:])
