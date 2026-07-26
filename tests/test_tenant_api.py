from django.test import TestCase
from tenants.models import Tenant

from tests.support import api_data, api_message


class TenantContextTests(TestCase):
    def setUp(self):
        """准备测试数据。"""
        Tenant.objects.create(slug="acme", name="Acme Corp")

    def test_tenant_scoped_api_resolves_tenant_from_slug(self):
        """验证租户 API 可从路径 slug 解析租户。"""
        response = self.client.get("/api/v1/acme/context/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            api_data(response),
            {
                "slug": "acme",
                "name": "Acme Corp",
                "timezone": "Asia/Shanghai",
                "is_active": True,
            },
        )

    def test_unknown_tenant_slug_returns_not_found(self):
        """验证未知租户 slug 返回 404。"""
        response = self.client.get("/api/v1/missing/context/")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(api_message(response), "租户不存在。")

    def test_inactive_tenant_slug_returns_forbidden(self):
        """验证已停用租户 slug 返回 403。"""
        Tenant.objects.create(slug="paused", name="Paused Corp", is_active=False)

        response = self.client.get("/api/v1/paused/context/")

        self.assertEqual(response.status_code, 403)
        self.assertEqual(api_message(response), "租户已停用。")
