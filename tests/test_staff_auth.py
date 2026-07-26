from accounts.models import StaffProfile
from django.contrib.auth.models import User
from rest_framework.test import APITestCase
from tenants.models import Tenant, TenantMembership, TenantRole

from tests.support import api_data, api_message


class StaffLoginTests(APITestCase):
    def setUp(self):
        """准备测试数据。"""
        user = User.objects.create_user(username="acme-admin", password="StrongPass123!")
        StaffProfile.objects.create(user=user, phone="13800138000")

    def test_staff_user_can_login_with_username_and_password(self):
        """验证后台用户可使用用户名和密码登录。"""
        response = self.client.post(
            "/api/v1/auth/staff/sessions/",
            {"login": "acme-admin", "password": "StrongPass123!"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        data = api_data(response)
        self.assertIn("access", data)
        self.assertIn("refresh", data)

    def test_staff_user_can_login_with_phone_and_password(self):
        """验证后台用户可使用手机号和密码登录。"""
        response = self.client.post(
            "/api/v1/auth/staff/sessions/",
            {"login": "13800138000", "password": "StrongPass123!"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        data = api_data(response)
        self.assertIn("access", data)
        self.assertIn("refresh", data)


class StaffTokenRefreshTests(APITestCase):
    def setUp(self):
        """准备测试数据。"""
        User.objects.create_user(username="acme-admin", password="StrongPass123!")

    def test_refresh_token_rotates_and_revokes_previous_token(self):
        """验证 refresh token 轮换后旧 token 失效。"""
        login_response = self.client.post(
            "/api/v1/auth/staff/sessions/",
            {"login": "acme-admin", "password": "StrongPass123!"},
            format="json",
        )
        original_refresh = api_data(login_response)["refresh"]

        refresh_response = self.client.post(
            "/api/v1/auth/tokens/refresh/",
            {"refresh": original_refresh},
            format="json",
        )

        self.assertEqual(refresh_response.status_code, 200)
        new_refresh = api_data(refresh_response)["refresh"]
        self.assertNotEqual(new_refresh, original_refresh)

        reuse_response = self.client.post(
            "/api/v1/auth/tokens/refresh/",
            {"refresh": original_refresh},
            format="json",
        )
        self.assertEqual(reuse_response.status_code, 401)


class StaffRoleAuthorizationTests(APITestCase):
    def setUp(self):
        """准备测试数据。"""
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
        """登录并返回 access token。"""
        response = self.client.post(
            "/api/v1/auth/staff/sessions/",
            {"login": login, "password": "StrongPass123!"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        return api_data(response)["access"]

    def test_unauthenticated_request_cannot_access_merchant_config(self):
        """验证未认证请求无法访问租户 records API。"""
        response = self.client.get("/api/v1/acme/records/")

        self.assertEqual(response.status_code, 401)

    def test_tenant_admin_with_jwt_can_access_merchant_config(self):
        """验证租户管理员 JWT 可访问 records API。"""
        access = self._login("tenant-admin")
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")

        response = self.client.get("/api/v1/acme/records/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(api_data(response)["records"], [])

    def test_staff_with_jwt_cannot_access_merchant_config(self):
        """验证普通 staff JWT 无法访问 records API。"""
        access = self._login("staff")
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")

        response = self.client.get("/api/v1/acme/records/")

        self.assertEqual(response.status_code, 403)
        self.assertEqual(api_message(response), "需要租户管理员权限。")

    def test_staff_with_jwt_can_access_own_tenant_membership(self):
        """验证 staff JWT 可访问所属租户 membership API。"""
        access = self._login("staff")
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")

        response = self.client.get("/api/v1/acme/membership/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(api_data(response)["role"], TenantRole.STAFF)

    def test_platform_admin_with_jwt_can_access_any_tenant_merchant_config(self):
        """验证平台超管 JWT 可访问任意租户 records API。"""
        access = self._login("platform-admin")
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")

        response = self.client.get("/api/v1/beta/records/")

        self.assertEqual(response.status_code, 200)

    def test_jwt_membership_mismatch_with_path_tenant_slug_is_rejected(self):
        """验证 JWT 租户成员与路径 slug 不匹配时被拒绝。"""
        access = self._login("tenant-admin")
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")

        response = self.client.get("/api/v1/beta/records/")

        self.assertEqual(response.status_code, 403)
        self.assertEqual(api_message(response), "无权访问该租户。")
