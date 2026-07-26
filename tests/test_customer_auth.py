from accounts.models import CustomerProfile
from accounts.services.sms import sms_sent_messages, sms_sent_messages_clear
from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import override_settings
from rest_framework.test import APITestCase
from tenants.models import Tenant, TenantCustomer


@override_settings(
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "customer-auth-tests",
        }
    },
    OTP_SEND_INTERVAL_SECONDS=60,
    OTP_DAILY_SEND_LIMIT=3,
    OTP_MAX_VERIFY_FAILURES=3,
    OTP_LOCK_SECONDS=300,
)
class CustomerOtpApiTests(APITestCase):
    def setUp(self):
        cache.clear()
        sms_sent_messages_clear()
        self.tenant = Tenant.objects.create(slug="acme", name="Acme Corp")
        self.other_tenant = Tenant.objects.create(slug="beta", name="Beta Corp")
        self.phone = "13900139000"

    def _send_otp(self, phone: str | None = None):
        return self.client.post(
            "/api/v1/auth/customer/otp/send/",
            {"phone": phone or self.phone},
            format="json",
        )

    def _latest_code(self, phone: str | None = None) -> str:
        phone = phone or self.phone
        for message in reversed(sms_sent_messages()):
            if message["phone"] == phone:
                return message["code"]
        raise AssertionError(f"未找到发给 {phone} 的验证码")

    def _verify(self, *, phone: str | None = None, code: str, tenant_slug: str = "acme"):
        return self.client.post(
            "/api/v1/auth/customer/otp/verify/",
            {
                "phone": phone or self.phone,
                "code": code,
                "tenant_slug": tenant_slug,
            },
            format="json",
        )

    def test_customer_can_request_otp_and_mock_sms_records_send(self):
        response = self._send_otp()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["detail"], "验证码已发送。")
        self.assertEqual(len(sms_sent_messages()), 1)
        self.assertEqual(sms_sent_messages()[0]["phone"], self.phone)
        self.assertRegex(sms_sent_messages()[0]["code"], r"^\d{6}$")

    def test_otp_send_interval_limit_is_enforced(self):
        first = self._send_otp()
        second = self._send_otp()

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 400)
        self.assertIn("发送过于频繁", str(second.json()))

    def test_otp_daily_send_limit_is_enforced(self):
        for _ in range(3):
            cache.delete(f"otp:cooldown:{self.phone}")
            response = self._send_otp()
            self.assertEqual(response.status_code, 200)

        cache.delete(f"otp:cooldown:{self.phone}")
        blocked = self._send_otp()

        self.assertEqual(blocked.status_code, 400)
        self.assertIn("今日发送次数已达上限", str(blocked.json()))

    def test_otp_verify_lock_after_consecutive_failures(self):
        self._send_otp()
        for _ in range(3):
            response = self._verify(code="000000")
            self.assertEqual(response.status_code, 400)

        locked = self._verify(code=self._latest_code())
        self.assertEqual(locked.status_code, 400)
        self.assertIn("验证过于频繁", str(locked.json()))

    def test_first_verify_creates_platform_account_and_returns_jwt(self):
        self._send_otp()
        response = self._verify(code=self._latest_code())

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn("access", body)
        self.assertIn("refresh", body)
        self.assertEqual(CustomerProfile.objects.filter(phone=self.phone).count(), 1)
        self.assertTrue(
            TenantCustomer.objects.filter(
                tenant=self.tenant,
                user__customer_profile__phone=self.phone,
            ).exists()
        )

    def test_repeat_login_does_not_create_duplicate_account(self):
        self._send_otp()
        first = self._verify(code=self._latest_code())
        self.assertEqual(first.status_code, 200)

        cache.delete(f"otp:cooldown:{self.phone}")
        self._send_otp()
        second = self._verify(code=self._latest_code())

        self.assertEqual(second.status_code, 200)
        self.assertEqual(CustomerProfile.objects.filter(phone=self.phone).count(), 1)
        self.assertEqual(User.objects.filter(username=f"customer_{self.phone}").count(), 1)

    def test_same_platform_account_has_independent_tenant_customer_profiles(self):
        self._send_otp()
        first = self._verify(code=self._latest_code(), tenant_slug="acme")
        self.assertEqual(first.status_code, 200)

        cache.delete(f"otp:cooldown:{self.phone}")
        self._send_otp()
        second = self._verify(code=self._latest_code(), tenant_slug="beta")
        self.assertEqual(second.status_code, 200)

        user = User.objects.get(customer_profile__phone=self.phone)
        self.assertEqual(TenantCustomer.objects.filter(user=user).count(), 2)
        self.assertTrue(TenantCustomer.objects.filter(user=user, tenant=self.tenant).exists())
        self.assertTrue(TenantCustomer.objects.filter(user=user, tenant=self.other_tenant).exists())

    def test_customer_jwt_can_access_tenant_scoped_customer_api(self):
        self._send_otp()
        login = self._verify(code=self._latest_code())
        access = login.json()["access"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")

        response = self.client.get("/api/v1/acme/customer/me/")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["tenant_slug"], "acme")
        self.assertEqual(body["phone"], self.phone)

    def test_customer_jwt_cannot_access_other_tenant_customer_api(self):
        self._send_otp()
        login = self._verify(code=self._latest_code(), tenant_slug="acme")
        access = login.json()["access"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")

        response = self.client.get("/api/v1/beta/customer/me/")

        self.assertEqual(response.status_code, 403)
