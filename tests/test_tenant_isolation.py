from django.contrib.auth.models import User
from rest_framework.test import APIClient, APITestCase
from tenants.models import Tenant, TenantMembership, TenantRole, TenantScopedRecord

from tests.support import api_data, api_message


class TenantMembershipTests(APITestCase):
    def setUp(self):
        """准备测试数据。"""
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
        """验证租户成员可访问所属租户 membership API。"""
        self.client.force_authenticate(user=self.member_a)

        response = self.client.get("/api/v1/tenant-a/membership/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(api_data(response)["role"], TenantRole.TENANT_ADMIN)

    def test_tenant_member_is_rejected_when_path_slug_does_not_match_membership(self):
        """验证路径 slug 与成员租户不匹配时返回 403。"""
        self.client.force_authenticate(user=self.member_a)

        response = self.client.get("/api/v1/tenant-b/membership/")

        self.assertEqual(response.status_code, 403)
        self.assertEqual(api_message(response), "无权访问该租户。")


class TenantIsolationTests(APITestCase):
    def setUp(self):
        """准备测试数据。"""
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
        self.record_a = TenantScopedRecord.objects.create(tenant=self.tenant_a, label="alpha")
        self.client = APIClient()

    def test_tenant_context_only_returns_data_for_path_tenant(self):
        """验证 context API 仅返回路径对应租户的数据。"""
        response = self.client.get("/api/v1/tenant-a/context/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(api_data(response)["slug"], "tenant-a")

    def test_tenant_member_cannot_read_other_tenant_records(self):
        """验证租户成员无法读取其他租户的 records。"""
        self.client.force_authenticate(user=self.member_b)

        response = self.client.get("/api/v1/tenant-a/records/")

        self.assertEqual(response.status_code, 403)

    def test_tenant_member_only_sees_own_tenant_records(self):
        """验证租户成员只能看到所属租户的 records。"""
        TenantScopedRecord.objects.create(tenant=self.tenant_b, label="beta")
        self.client.force_authenticate(user=self.member_a)

        response = self.client.get("/api/v1/tenant-a/records/")

        self.assertEqual(response.status_code, 200)
        records = api_data(response)["records"]
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["label"], "alpha")
        self.assertEqual(records[0]["id"], self.record_a.id)

    def test_tenant_member_cannot_create_record_in_other_tenant(self):
        """验证租户成员无法在其他租户下创建 record。"""
        self.client.force_authenticate(user=self.member_b)

        response = self.client.post(
            "/api/v1/tenant-a/records/", {"label": "intrusion"}, format="json"
        )

        self.assertEqual(response.status_code, 403)
        self.assertFalse(
            TenantScopedRecord.objects.filter(tenant=self.tenant_a, label="intrusion").exists()
        )
