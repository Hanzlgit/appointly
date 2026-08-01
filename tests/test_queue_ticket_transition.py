"""QueueTicket 状态变更 Service 测试。"""

from uuid import uuid4

from catalog.models import Location, Service, Stylist
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import TestCase

from queuing.models import QueueTicketStatus
from queuing.services.ticket_create import queue_ticket_create
from queuing.services.ticket_transition import (
    queue_ticket_call,
    queue_ticket_cancel,
    queue_ticket_complete,
    queue_ticket_move_to_tail,
    queue_ticket_start,
)


class QueueTicketTransitionTests(TestCase):
    """叫号生命周期测试。"""

    stylist: Stylist
    service: Service
    customer: User

    def setUp(self):
        """准备取号环境。"""
        location = Location.objects.create(name="万达店")
        self.stylist = Stylist.objects.create(location=location, name="A剪发师", ticket_prefix="A")
        self.service = Service.objects.create(
            stylist=self.stylist,
            name="男士洗剪吹",
            duration_minutes=45,
            price_cents=6800,
        )
        self.customer = User.objects.create_user(username="customer-1")

    def _create_ticket(self) -> int:
        """取号并返回 ticket ID。"""
        ticket = queue_ticket_create(
            customer=self.customer,
            stylist_id=self.stylist.id,
            service_id=self.service.id,
            idempotency_key=str(uuid4()),
        )
        return ticket.id

    def test_queue_ticket_call_moves_waiting_to_called(self):
        """叫号后状态变为 called。"""
        ticket_id = self._create_ticket()
        ticket = queue_ticket_call(ticket_id=ticket_id)

        self.assertEqual(ticket.status, QueueTicketStatus.CALLED)
        self.assertIsNotNone(ticket.called_at)

    def test_queue_ticket_start_moves_called_to_serving(self):
        """确认到场后状态变为 serving。"""
        ticket_id = self._create_ticket()
        queue_ticket_call(ticket_id=ticket_id)
        ticket = queue_ticket_start(ticket_id=ticket_id)

        self.assertEqual(ticket.status, QueueTicketStatus.SERVING)
        self.assertIsNotNone(ticket.serving_started_at)

    def test_queue_ticket_complete_moves_serving_to_completed(self):
        """完成后状态变为 completed。"""
        ticket_id = self._create_ticket()
        queue_ticket_call(ticket_id=ticket_id)
        queue_ticket_start(ticket_id=ticket_id)
        ticket = queue_ticket_complete(ticket_id=ticket_id)

        self.assertEqual(ticket.status, QueueTicketStatus.COMPLETED)

    def test_queue_ticket_cancel_by_customer_only_when_waiting(self):
        """顾客仅能在 waiting 状态自行取消。"""
        ticket_id = self._create_ticket()
        ticket = queue_ticket_cancel(ticket_id=ticket_id, by_customer=True)

        self.assertEqual(ticket.status, QueueTicketStatus.CANCELLED)

    def test_queue_ticket_cancel_by_customer_rejects_called_status(self):
        """已叫号后顾客不能自行取消。"""
        ticket_id = self._create_ticket()
        queue_ticket_call(ticket_id=ticket_id)

        with self.assertRaises(ValidationError):
            queue_ticket_cancel(ticket_id=ticket_id, by_customer=True)

    def test_queue_ticket_move_to_tail_requeues_called_ticket(self):
        """已叫号未到场的号移回 waiting 并排至队尾。"""
        first = User.objects.create_user(username="first")
        second = User.objects.create_user(username="second")
        first_ticket = queue_ticket_create(
            customer=first,
            stylist_id=self.stylist.id,
            service_id=self.service.id,
            idempotency_key=str(uuid4()),
        )
        second_ticket = queue_ticket_create(
            customer=second,
            stylist_id=self.stylist.id,
            service_id=self.service.id,
            idempotency_key=str(uuid4()),
        )
        queue_ticket_call(ticket_id=first_ticket.id)
        moved = queue_ticket_move_to_tail(ticket_id=first_ticket.id)

        self.assertEqual(moved.status, QueueTicketStatus.WAITING)
        self.assertIsNone(moved.called_at)
        self.assertGreater(moved.position, second_ticket.position)
