"""公开浏览服务列表 API 测试。"""

from catalog.models import Location, Service, Stylist
from django.test import TestCase
from rest_framework.test import APIClient

from tests.support import api_code, api_data


class CatalogPublicServiceListTests(TestCase):
    """未登录用户可浏览理发师服务。"""

    def setUp(self):
        """准备门店、理发师与服务。"""
        self.client = APIClient()
        location = Location.objects.create(name="万达店")
        self.stylist = Stylist.objects.create(location=location, name="A剪发师", ticket_prefix="A")
        Service.objects.create(
            stylist=self.stylist,
            name="男士洗剪吹",
            duration_minutes=45,
            price_cents=6800,
        )

    def test_anonymous_user_can_list_stylist_services(self):
        """未登录访问服务列表返回 200。"""
        response = self.client.get(f"/api/v1/stylists/{self.stylist.id}/services/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(api_code(response), 0)
        data = api_data(response)
        self.assertEqual(data["total"], 1)
        self.assertEqual(data["items"][0]["name"], "男士洗剪吹")
