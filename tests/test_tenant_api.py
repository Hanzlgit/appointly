from django.test import TestCase
from tenants.models import Tenant


class TenantContextApiTests(TestCase):
    def setUp(self):
        Tenant.objects.create(slug="acme", name="Acme Corp")

    def test_tenant_scoped_api_resolves_tenant_from_slug(self):
        response = self.client.get("/api/v1/acme/context/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "slug": "acme",
                "name": "Acme Corp",
                "timezone": "Asia/Shanghai",
                "is_active": True,
            },
        )

    def test_unknown_tenant_slug_returns_not_found(self):
        response = self.client.get("/api/v1/missing/context/")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["detail"], "租户不存在。")

    def test_inactive_tenant_slug_returns_forbidden(self):
        Tenant.objects.create(slug="paused", name="Paused Corp", is_active=False)

        response = self.client.get("/api/v1/paused/context/")

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "租户已停用。")
