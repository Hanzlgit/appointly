from accounts.models import StaffProfile
from django.contrib.auth.models import User
from rest_framework.test import APITestCase
from tenants.models import Tenant, TenantMembership, TenantRole


class StaffLoginApiTests(APITestCase):
    def setUp(self):
        user = User.objects.create_user(username="acme-admin", password="StrongPass123!")
        StaffProfile.objects.create(user=user, phone="13800138000")

    def test_staff_user_can_login_with_username_and_password(self):
        response = self.client.post(
            "/api/v1/auth/login/",
            {"login": "acme-admin", "password": "StrongPass123!"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn("access", body)
        self.assertIn("refresh", body)

    def test_staff_user_can_login_with_phone_and_password(self):
        response = self.client.post(
            "/api/v1/auth/login/",
            {"login": "13800138000", "password": "StrongPass123!"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn("access", body)
        self.assertIn("refresh", body)


class StaffTokenRefreshApiTests(APITestCase):
    def setUp(self):
        User.objects.create_user(username="acme-admin", password="StrongPass123!")

    def test_refresh_token_rotates_and_revokes_previous_token(self):
        login_response = self.client.post(
            "/api/v1/auth/login/",
            {"login": "acme-admin", "password": "StrongPass123!"},
            format="json",
        )
        original_refresh = login_response.json()["refresh"]

        refresh_response = self.client.post(
            "/api/v1/auth/token/refresh/",
            {"refresh": original_refresh},
            format="json",
        )

        self.assertEqual(refresh_response.status_code, 200)
        new_refresh = refresh_response.json()["refresh"]
        self.assertNotEqual(new_refresh, original_refresh)

        reuse_response = self.client.post(
            "/api/v1/auth/token/refresh/",
            {"refresh": original_refresh},
            format="json",
        )
        self.assertEqual(reuse_response.status_code, 401)


class StaffRoleAuthorizationApiTests(APITestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(slug="acme", name="Acme Corp")
        self.other_tenant = Tenant.objects.create(slug="beta", name="Beta Corp")

        self.tenant_admin = User.objects.create_user(
            username="tenant-admin", password="StrongPass123!"
        )
        TenantMembership.objects.create(
            tenant=self.tenant,
            user=self.tenant_admin,
            role=TenantRole.TENANT_ADMIN,
        )

        self.staff_user = User.objects.create_user(username="staff", password="StrongPass123!")
        TenantMembership.objects.create(
            tenant=self.tenant,
            user=self.staff_user,
            role=TenantRole.STAFF,
        )

        self.platform_admin = User.objects.create_superuser(
            username="platform-admin",
            email="admin@example.com",
            password="StrongPass123!",
        )

    def _login(self, login: str) -> str:
        response = self.client.post(
            "/api/v1/auth/login/",
            {"login": login, "password": "StrongPass123!"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        return response.json()["access"]

    def test_unauthenticated_request_cannot_access_merchant_config(self):
        response = self.client.get("/api/v1/acme/records/")

        self.assertEqual(response.status_code, 401)

    def test_tenant_admin_with_jwt_can_access_merchant_config(self):
        access = self._login("tenant-admin")
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")

        response = self.client.get("/api/v1/acme/records/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["labels"], [])

    def test_staff_with_jwt_cannot_access_merchant_config(self):
        access = self._login("staff")
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")

        response = self.client.get("/api/v1/acme/records/")

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "需要租户管理员权限。")

    def test_staff_with_jwt_can_access_own_tenant_membership(self):
        access = self._login("staff")
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")

        response = self.client.get("/api/v1/acme/membership/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["role"], TenantRole.STAFF)

    def test_platform_admin_with_jwt_can_access_any_tenant_merchant_config(self):
        access = self._login("platform-admin")
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")

        response = self.client.get("/api/v1/beta/records/")

        self.assertEqual(response.status_code, 200)

    def test_jwt_membership_mismatch_with_path_tenant_slug_is_rejected(self):
        access = self._login("tenant-admin")
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")

        response = self.client.get("/api/v1/beta/records/")

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "无权访问该租户。")
