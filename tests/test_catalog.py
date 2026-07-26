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
        self.assertEqual(location["resource_ids"], [])


class CatalogLocationListTests(CatalogAdminMixin, APITestCase):
    def test_tenant_admin_can_list_locations(self):
        """验证租户管理员可列出服务地点。"""
        self.client.post(
            "/api/v1/acme/catalog/locations/",
            {"name": "North Branch"},
            format="json",
        )

        response = self.client.get("/api/v1/acme/catalog/locations/")

        self.assertEqual(response.status_code, 200)
        locations = api_data(response)["locations"]
        self.assertEqual(len(locations), 1)
        self.assertEqual(locations[0]["name"], "North Branch")


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


class CatalogServiceTests(CatalogAdminMixin, APITestCase):
    def test_tenant_admin_can_create_service(self):
        """验证租户管理员可创建服务项目。"""
        response = self.client.post(
            "/api/v1/acme/catalog/services/",
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
        self.assertEqual(service["resource_ids"], [])


class CatalogResourceTests(CatalogAdminMixin, APITestCase):
    def setUp(self):
        """准备租户管理员与 staff 用户。"""
        super().setUp()
        self.staff_user = User.objects.create_user(username="stylist", password="StrongPass123!")
        TenantMembership.objects.create(
            tenant=self.tenant,
            user=self.staff_user,
            role=TenantRole.STAFF,
        )

    def test_tenant_admin_can_create_resource_with_optional_staff_user(self):
        """验证租户管理员可创建资源并可选关联工作人员。"""
        response = self.client.post(
            "/api/v1/acme/catalog/resources/",
            {
                "name": "Alice",
                "resource_type": "staff",
                "staff_user_id": self.staff_user.id,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        resource = api_data(response)
        self.assertEqual(resource["name"], "Alice")
        self.assertEqual(resource["resource_type"], "staff")
        self.assertEqual(resource["staff_user_id"], self.staff_user.id)


class CatalogM2MTests(CatalogAdminMixin, APITestCase):
    def test_location_and_service_can_link_resources(self):
        """验证地点与服务均可配置资源多对多关联。"""
        resource_response = self.client.post(
            "/api/v1/acme/catalog/resources/",
            {"name": "Room A", "resource_type": "room"},
            format="json",
        )
        resource_id = api_data(resource_response)["id"]

        location_response = self.client.post(
            "/api/v1/acme/catalog/locations/",
            {"name": "Main Hall", "resource_ids": [resource_id]},
            format="json",
        )
        self.assertEqual(api_data(location_response)["resource_ids"], [resource_id])

        service_response = self.client.post(
            "/api/v1/acme/catalog/services/",
            {
                "name": "Consultation",
                "duration_minutes": 60,
                "resource_ids": [resource_id],
            },
            format="json",
        )
        self.assertEqual(api_data(service_response)["resource_ids"], [resource_id])


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
            name="Active Service",
            duration_minutes=30,
            is_active=True,
        )
        Service.objects.create(
            tenant=self.tenant,
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
            name="Alice",
            resource_type="staff",
            is_active=True,
        )
        resource.locations.add(self.active_location)
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
        Location.objects.create(tenant=self.tenant_a, name="A Location")
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
        Location.objects.create(tenant=self.tenant_b, name="B Location")

        response = self.client.get("/api/v1/tenant-a/catalog/locations/")

        self.assertEqual(response.status_code, 200)
        locations = api_data(response)["locations"]
        self.assertEqual(len(locations), 1)
        self.assertEqual(locations[0]["name"], "A Location")


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
