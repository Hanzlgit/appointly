"""QueueTicket 取号 Service 层测试（TDD 主接缝）。"""

from uuid import uuid4

from catalog.models import Location, Service, Stylist, StylistQueueStatus
from django.contrib.auth.models import User
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings

from queuing.models import ACTIVE_QUEUE_TICKET_STATUSES, QueueTicket, QueueTicketStatus
from queuing.services.ticket_create import queue_ticket_create


@override_settings(
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "queue-ticket-create-tests",
        }
    },
)
class QueueTicketCreateTests(TestCase):
    """取号业务规则测试。"""

    location: Location
    stylist: Stylist
    service: Service
    customer: User

    def setUp(self):
        """准备门店、理发师、服务与顾客。"""
        cache.clear()
        self.location = Location.objects.create(name="万达店", address="万达广场 1F")
        self.stylist = Stylist.objects.create(
            location=self.location,
            name="A剪发师",
            ticket_prefix="A",
            queue_status=StylistQueueStatus.OPEN,
        )
        self.service = Service.objects.create(
            stylist=self.stylist,
            name="男士洗剪吹",
            duration_minutes=45,
            price_cents=6800,
        )
        self.customer = User.objects.create_user(username="customer-1")

    def test_queue_ticket_create_assigns_first_ticket_number(self):
        """首位取号顾客获得当日 1 号。"""
        ticket = queue_ticket_create(
            customer=self.customer,
            stylist_id=self.stylist.id,
            service_id=self.service.id,
            idempotency_key=str(uuid4()),
        )

        self.assertEqual(ticket.ticket_number, 1)
        self.assertEqual(ticket.status, QueueTicketStatus.WAITING)
        self.assertEqual(ticket.position, 1)
        self.assertEqual(ticket.stylist_id, self.stylist.id)
        self.assertEqual(ticket.service_id, self.service.id)

    def test_queue_ticket_create_increments_ticket_number_for_same_stylist(self):
        """同一理发师第二位顾客获得 2 号。"""
        other = User.objects.create_user(username="customer-2")
        queue_ticket_create(
            customer=self.customer,
            stylist_id=self.stylist.id,
            service_id=self.service.id,
            idempotency_key=str(uuid4()),
        )
        second = queue_ticket_create(
            customer=other,
            stylist_id=self.stylist.id,
            service_id=self.service.id,
            idempotency_key=str(uuid4()),
        )

        self.assertEqual(second.ticket_number, 2)
        self.assertEqual(second.position, 2)

    def test_queue_ticket_create_rejects_second_active_ticket_for_same_customer(self):
        """同一顾客不能同时持有两个有效排队号。"""
        queue_ticket_create(
            customer=self.customer,
            stylist_id=self.stylist.id,
            service_id=self.service.id,
            idempotency_key=str(uuid4()),
        )

        with self.assertRaises(ValidationError):
            queue_ticket_create(
                customer=self.customer,
                stylist_id=self.stylist.id,
                service_id=self.service.id,
                idempotency_key=str(uuid4()),
            )

    def test_queue_ticket_create_is_idempotent(self):
        """相同幂等键重试返回首次创建的排队号。"""
        idempotency_key = str(uuid4())
        first = queue_ticket_create(
            customer=self.customer,
            stylist_id=self.stylist.id,
            service_id=self.service.id,
            idempotency_key=idempotency_key,
        )
        second = queue_ticket_create(
            customer=self.customer,
            stylist_id=self.stylist.id,
            service_id=self.service.id,
            idempotency_key=idempotency_key,
        )

        self.assertEqual(first.id, second.id)
        self.assertEqual(QueueTicket.objects.count(), 1)

    def test_queue_ticket_create_rejects_when_stylist_not_open(self):
        """暂停或关闭接单的理发师不可取号。"""
        self.stylist.queue_status = StylistQueueStatus.PAUSED
        self.stylist.save(update_fields=["queue_status"])

        with self.assertRaises(ValidationError):
            queue_ticket_create(
                customer=self.customer,
                stylist_id=self.stylist.id,
                service_id=self.service.id,
                idempotency_key=str(uuid4()),
            )

    def test_queue_ticket_create_rejects_service_not_owned_by_stylist(self):
        """不能为理发师选择其未提供的服务。"""
        other_stylist = Stylist.objects.create(
            location=self.location,
            name="B剪发师",
            ticket_prefix="B",
        )
        other_service = Service.objects.create(
            stylist=other_stylist,
            name="女士洗剪吹",
            duration_minutes=60,
            price_cents=9800,
        )

        with self.assertRaises(ValidationError):
            queue_ticket_create(
                customer=self.customer,
                stylist_id=self.stylist.id,
                service_id=other_service.id,
                idempotency_key=str(uuid4()),
            )
