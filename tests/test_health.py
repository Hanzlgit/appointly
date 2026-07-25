from django.test import TestCase
from django.urls import reverse


class HealthCheckTests(TestCase):
    def test_live_endpoint(self):
        response = self.client.get("/health/live")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")

    def test_ready_endpoint(self):
        response = self.client.get("/health/ready")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ready")


class PingTests(TestCase):
    def test_ping(self):
        response = self.client.get(reverse("ping"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")
