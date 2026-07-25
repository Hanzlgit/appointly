from django.contrib.auth.models import User
from rest_framework.test import APIClient, APITestCase
from tenants.models import Tenant, TenantMembership, TenantRole, TenantScopedRecord


class TenantMembershipApiTests(APITestCase):
    def setUp(self):
        self.tenant_a = Tenant.objects.create(slug="tenant-a", name="Tenant A")
        self.tenant_b = Tenant.objects.create(slug="tenant-b", name="Tenant B")
        self.member_a = User.objects.create_user(username="member-a", password="pass-123")
        TenantMembership.objects.create(
            tenant=self.tenant_a,
            user=self.member_a,
            role=TenantRole.TENANT_ADMIN,
        )
        self.client = APIClient()

    def test_tenant_member_can_access_own_tenant_membership(self):
        self.client.force_authenticate(user=self.member_a)

        response = self.client.get("/api/v1/tenant-a/membership/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["role"], TenantRole.TENANT_ADMIN)

    def test_tenant_member_is_rejected_when_path_slug_does_not_match_membership(self):
        self.client.force_authenticate(user=self.member_a)

        response = self.client.get("/api/v1/tenant-b/membership/")

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "无权访问该租户。")


class TenantIsolationApiTests(APITestCase):
    def setUp(self):
        self.tenant_a = Tenant.objects.create(slug="tenant-a", name="Tenant A")
        self.tenant_b = Tenant.objects.create(slug="tenant-b", name="Tenant B")
        self.member_a = User.objects.create_user(username="member-a", password="pass-123")
        self.member_b = User.objects.create_user(username="member-b", password="pass-123")
        TenantMembership.objects.create(
            tenant=self.tenant_a,
            user=self.member_a,
            role=TenantRole.TENANT_ADMIN,
        )
        TenantMembership.objects.create(
            tenant=self.tenant_b,
            user=self.member_b,
            role=TenantRole.TENANT_ADMIN,
        )
        TenantScopedRecord.objects.create(tenant=self.tenant_a, label="alpha")
        self.client = APIClient()

    def test_tenant_context_only_returns_data_for_path_tenant(self):
        response = self.client.get("/api/v1/tenant-a/context/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["slug"], "tenant-a")

    def test_tenant_member_cannot_read_other_tenant_records(self):
        self.client.force_authenticate(user=self.member_b)

        response = self.client.get("/api/v1/tenant-a/records/")

        self.assertEqual(response.status_code, 403)

    def test_tenant_member_only_sees_own_tenant_records(self):
        TenantScopedRecord.objects.create(tenant=self.tenant_b, label="beta")
        self.client.force_authenticate(user=self.member_a)

        response = self.client.get("/api/v1/tenant-a/records/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["labels"], ["alpha"])

    def test_tenant_member_cannot_create_record_in_other_tenant(self):
        self.client.force_authenticate(user=self.member_b)

        response = self.client.post(
            "/api/v1/tenant-a/records/", {"label": "intrusion"}, format="json"
        )

        self.assertEqual(response.status_code, 403)
        self.assertFalse(
            TenantScopedRecord.objects.filter(tenant=self.tenant_a, label="intrusion").exists()
        )
