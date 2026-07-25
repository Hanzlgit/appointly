from django.contrib.auth.models import User
from django.test import TestCase
from tenants.models import Tenant, TenantMembership, TenantRole


class TenantAdminTests(TestCase):
    def setUp(self):
        self.admin_user = User.objects.create_superuser(
            username="platform-admin",
            email="admin@example.com",
            password="admin-pass-123",
        )
        self.client.force_login(self.admin_user)

    def test_platform_admin_can_create_tenant_with_default_timezone(self):
        response = self.client.post(
            "/admin/tenants/tenant/add/",
            {
                "slug": "acme",
                "name": "Acme Corp",
                "timezone": "Asia/Shanghai",
                "is_active": "on",
            },
        )

        self.assertEqual(response.status_code, 302)
        tenant = Tenant.objects.get(slug="acme")
        self.assertEqual(tenant.name, "Acme Corp")
        self.assertEqual(tenant.timezone, "Asia/Shanghai")
        self.assertTrue(tenant.is_active)

    def test_platform_admin_can_create_first_tenant_admin_membership(self):
        tenant = Tenant.objects.create(slug="acme", name="Acme Corp")

        response = self.client.post(
            "/admin/auth/user/add/",
            {
                "username": "acme-admin",
                "password1": "StrongPass123!",
                "password2": "StrongPass123!",
                "tenant_memberships-TOTAL_FORMS": "1",
                "tenant_memberships-INITIAL_FORMS": "0",
                "tenant_memberships-MIN_NUM_FORMS": "0",
                "tenant_memberships-MAX_NUM_FORMS": "1",
                "tenant_memberships-0-tenant": str(tenant.pk),
                "tenant_memberships-0-role": TenantRole.TENANT_ADMIN,
            },
        )

        self.assertEqual(response.status_code, 302)
        user = User.objects.get(username="acme-admin")
        membership = TenantMembership.objects.get(user=user, tenant=tenant)
        self.assertEqual(membership.role, TenantRole.TENANT_ADMIN)

    def test_platform_admin_can_deactivate_tenant(self):
        tenant = Tenant.objects.create(slug="acme", name="Acme Corp")

        response = self.client.post(
            f"/admin/tenants/tenant/{tenant.pk}/change/",
            {
                "slug": tenant.slug,
                "name": tenant.name,
                "timezone": tenant.timezone,
            },
        )

        self.assertEqual(response.status_code, 302)
        tenant.refresh_from_db()
        self.assertFalse(tenant.is_active)
