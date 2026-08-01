"""QueueTicket Outbox 测试。"""

from uuid import uuid4

from accounts.models import CustomerProfile
from catalog.models import Location, Service, Stylist
from django.contrib.auth.models import User
from django.test import TestCase

from notifications.models import OutboxEvent
from queuing.services.ticket_create import queue_ticket_create


class QueueTicketOutboxTests(TestCase):
    """取号 Outbox 事件测试。"""

    def test_queue_ticket_create_writes_outbox_event(self):
        """取号成功同事务写入 queue.ticket.created。"""
        location = Location.objects.create(name="万达店")
        stylist = Stylist.objects.create(location=location, name="A剪发师", ticket_prefix="A")
        service = Service.objects.create(
            stylist=stylist,
            name="男士洗剪吹",
            duration_minutes=45,
            price_cents=6800,
        )
        user = User.objects.create_user(username="customer-1")
        CustomerProfile.objects.create(user=user, phone="13900139000")

        ticket = queue_ticket_create(
            customer=user,
            stylist_id=stylist.id,
            service_id=service.id,
            idempotency_key=str(uuid4()),
        )

        event = OutboxEvent.objects.get(aggregate_id=ticket.id)
        self.assertEqual(event.event_type, "queue.ticket.created")
        self.assertEqual(event.payload["recipient_user_id"], user.id)
        self.assertIn("前面 0 人", event.payload["body"])
