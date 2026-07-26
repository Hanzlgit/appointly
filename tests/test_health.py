from django.test import TestCase
from django.urls import reverse

from tests.support import api_data


class HealthCheckTests(TestCase):
    def test_live_endpoint_returns_ok(self):
        """验证 live 健康检查端点返回 ok。"""
        response = self.client.get("/health/live")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")

    def test_ready_endpoint_returns_ready(self):
        """验证 ready 健康检查端点返回 ready。"""
        response = self.client.get("/health/ready")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ready")


class PingTests(TestCase):
    def test_ping_returns_ok(self):
        """验证 ping 端点返回 ok。"""
        response = self.client.get(reverse("ping"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(api_data(response)["status"], "ok")
