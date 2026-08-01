"""QueueTicket 排队指标 Selector 测试。"""

from uuid import uuid4

from catalog.models import Location, Service, Stylist
from django.contrib.auth.models import User
from django.test import TestCase

from queuing.models import QueueTicketStatus
from queuing.selectors import queue_ticket_ahead_count, queue_ticket_estimated_wait_minutes
from queuing.services.ticket_create import queue_ticket_create
from queuing.services.ticket_transition import queue_ticket_start


class QueueTicketSelectorTests(TestCase):
    """排队指标计算测试。"""

    stylist: Stylist
    service_short: Service
    service_long: Service

    def setUp(self):
        """准备理发师与两种时长服务。"""
        location = Location.objects.create(name="万达店")
        self.stylist = Stylist.objects.create(location=location, name="A剪发师", ticket_prefix="A")
        self.service_short = Service.objects.create(
            stylist=self.stylist,
            name="儿童单剪",
            duration_minutes=20,
            price_cents=3000,
        )
        self.service_long = Service.objects.create(
            stylist=self.stylist,
            name="男士洗剪吹",
            duration_minutes=45,
            price_cents=6800,
        )

    def _take(self, *, username: str, service: Service) -> User:
        """创建顾客并取号。"""
        user = User.objects.create_user(username=username)
        queue_ticket_create(
            customer=user,
            stylist_id=self.stylist.id,
            service_id=service.id,
            idempotency_key=str(uuid4()),
        )
        return user

    def test_queue_ticket_ahead_count_for_third_in_queue(self):
        """第三位顾客前面应有 2 人。"""
        self._take(username="u1", service=self.service_short)
        self._take(username="u2", service=self.service_long)
        third_user = self._take(username="u3", service=self.service_short)
        ticket = third_user.queue_tickets.get()

        self.assertEqual(queue_ticket_ahead_count(ticket=ticket), 2)

    def test_queue_ticket_estimated_wait_sums_ahead_service_durations(self):
        """预计等待为前方服务时长之和。"""
        self._take(username="u1", service=self.service_short)
        self._take(username="u2", service=self.service_long)
        third_user = self._take(username="u3", service=self.service_short)
        ticket = third_user.queue_tickets.get()

        self.assertEqual(queue_ticket_estimated_wait_minutes(ticket=ticket), 20 + 45)

    def test_queue_ticket_estimated_wait_includes_serving_ticket(self):
        """前方 waiting 时长加上当前 serving 服务时长。"""
        first_user = self._take(username="u1", service=self.service_long)
        second_user = self._take(username="u2", service=self.service_short)
        first_ticket = first_user.queue_tickets.get()
        from queuing.services.ticket_transition import queue_ticket_call

        queue_ticket_call(ticket_id=first_ticket.id)
        queue_ticket_start(ticket_id=first_ticket.id)
        ticket = second_user.queue_tickets.get()

        self.assertEqual(queue_ticket_estimated_wait_minutes(ticket=ticket), 45)
