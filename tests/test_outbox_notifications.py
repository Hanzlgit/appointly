"""Outbox 发布与站内通知测试。"""

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from accounts.models import CustomerProfile
from accounts.services.sms import sms_sent_message_clear, sms_sent_message_list
from catalog.models import Location, Resource, Service
from django.contrib.auth.models import User
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APITestCase
from scheduling.models import Booking, BookingCancelActor, BookingStatus, TimeSlot, TimeSlotStatus
from scheduling.services.booking_create import scheduling_booking_create
from scheduling.services.booking_transition import (
    scheduling_booking_cancel,
    scheduling_booking_confirm,
    scheduling_booking_reschedule,
)
from tenants.models import Tenant, TenantCustomer


@override_settings(
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "outbox-notification-tests",
        }
    },
    OTP_SEND_INTERVAL_SECONDS=60,
    CELERY_TASK_ALWAYS_EAGER=True,
)
class OutboxBookingTransactionTests(TestCase):
    """预约业务与 Outbox 同事务提交/回滚。"""

    def setUp(self):
        """准备租户、目录、时段与客户。"""
        cache.clear()
        sms_sent_message_clear()
        self.tenant = Tenant.objects.create(
            slug="acme",
            name="Acme Corp",
            timezone="Asia/Shanghai",
        )
        self.location = Location.objects.create(tenant=self.tenant, name="Main Studio")
        self.resource = Resource.objects.create(
            tenant=self.tenant,
            location=self.location,
            name="Alice",
        )
        self.service = Service.objects.create(
            tenant=self.tenant,
            location=self.location,
            name="Haircut",
            duration_minutes=60,
        )
        self.service.resources.add(self.resource)

        tenant_tz = ZoneInfo("Asia/Shanghai")
        slot_start = datetime(2026, 8, 1, 9, 0, tzinfo=tenant_tz).astimezone(UTC)
        slot_end = datetime(2026, 8, 1, 10, 0, tzinfo=tenant_tz).astimezone(UTC)
        self.time_slot = TimeSlot.objects.create(
            tenant=self.tenant,
            location=self.location,
            resource=self.resource,
            start=slot_start,
            end=slot_end,
            capacity=1,
            status=TimeSlotStatus.OPEN,
        )

        self.user = User.objects.create_user(username="customer-1")
        CustomerProfile.objects.create(user=self.user, phone="13900139000")
        self.customer = TenantCustomer.objects.create(tenant=self.tenant, user=self.user)

    def test_booking_create_writes_outbox_event_in_same_transaction(self):
        """成功创建预约时同事务写入 Outbox 事件。"""
        from notifications.models import OutboxEvent

        booking = scheduling_booking_create(
            tenant=self.tenant,
            customer=self.customer,
            idempotency_key="create-1",
            service_id=self.service.id,
            party_size=1,
            time_slot_id=self.time_slot.id,
        )

        events = OutboxEvent.objects.filter(aggregate_id=booking.id)
        self.assertEqual(events.count(), 1)
        self.assertEqual(events.first().event_type, "booking.confirmed")

    def test_booking_create_rollback_leaves_no_outbox_event(self):
        """业务回滚时 Outbox 事件不残留。"""
        from notifications.models import OutboxEvent

        full_slot = TimeSlot.objects.create(
            tenant=self.tenant,
            location=self.location,
            resource=self.resource,
            start=self.time_slot.start + timedelta(days=1),
            end=self.time_slot.end + timedelta(days=1),
            capacity=1,
            status=TimeSlotStatus.OPEN,
        )
        scheduling_booking_create(
            tenant=self.tenant,
            customer=self.customer,
            idempotency_key="fill-slot",
            service_id=self.service.id,
            party_size=1,
            time_slot_id=full_slot.id,
        )

        other_user = User.objects.create_user(username="customer-2")
        CustomerProfile.objects.create(user=other_user, phone="13900139001")
        other_customer = TenantCustomer.objects.create(tenant=self.tenant, user=other_user)

        with self.assertRaises(ValidationError):
            scheduling_booking_create(
                tenant=self.tenant,
                customer=other_customer,
                idempotency_key="fail-capacity",
                service_id=self.service.id,
                party_size=1,
                time_slot_id=full_slot.id,
            )

        self.assertEqual(OutboxEvent.objects.filter(event_type="booking.confirmed").count(), 1)


@override_settings(
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "outbox-publish-tests",
        }
    },
    CELERY_TASK_ALWAYS_EAGER=True,
)
class OutboxPublishTests(TestCase):
    """Outbox 发布任务重试与投递。"""

    def setUp(self):
        """准备未发布的 Outbox 事件。"""
        from notifications.models import OutboxEvent
        from notifications.services.messaging import broker_message_clear

        broker_message_clear()
        self.tenant = Tenant.objects.create(slug="pub", name="Pub Tenant")
        self.event = OutboxEvent.objects.create(
            tenant=self.tenant,
            event_type="booking.confirmed",
            aggregate_type="booking",
            aggregate_id=42,
            payload={"booking_id": 42},
        )

    def test_publish_task_retries_unpublished_events_to_broker(self):
        """发布任务将未发布事件投递到消息代理。"""
        from notifications.models import OutboxEvent
        from notifications.services.messaging import broker_message_list
        from notifications.tasks import notifications_publish_outbox_events

        notifications_publish_outbox_events()

        self.event.refresh_from_db()
        self.assertIsNotNone(self.event.published_at)
        messages = broker_message_list()
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0]["event_id"], str(self.event.event_id))
        self.assertEqual(OutboxEvent.objects.filter(published_at__isnull=True).count(), 0)


@override_settings(CELERY_TASK_ALWAYS_EAGER=True)
class OutboxConsumeIdempotencyTests(TestCase):
    """消费者按事件 ID 幂等处理。"""

    def setUp(self):
        """准备租户、用户与 Outbox 事件。"""
        from notifications.models import OutboxEvent

        sms_sent_message_clear()
        self.tenant = Tenant.objects.create(slug="consume", name="Consume Tenant")
        self.user = User.objects.create_user(username="notify-user")
        CustomerProfile.objects.create(user=self.user, phone="13900139999")
        self.event = OutboxEvent.objects.create(
            tenant=self.tenant,
            event_type="booking.confirmed",
            aggregate_type="booking",
            aggregate_id=1,
            payload={
                "tenant_id": self.tenant.id,
                "booking_id": 1,
                "recipient_user_id": self.user.id,
                "title": "预约已确认",
                "body": "您的预约已确认。",
                "phone": "13900139999",
            },
        )

    def test_duplicate_consume_produces_single_notification(self):
        """重复消费同一事件 ID 只产生一条站内通知。"""
        from notifications.models import Notification
        from notifications.services.consume import notifications_outbox_event_consume

        payload = {
            "event_id": str(self.event.event_id),
            "event_type": self.event.event_type,
            "payload": self.event.payload,
        }
        notifications_outbox_event_consume(**payload)
        notifications_outbox_event_consume(**payload)

        self.assertEqual(
            Notification.objects.filter(source_event_id=self.event.event_id).count(),
            1,
        )


@override_settings(
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "inapp-notification-tests",
        }
    },
    OTP_SEND_INTERVAL_SECONDS=60,
    CELERY_TASK_ALWAYS_EAGER=True,
)
class InAppNotificationRecipientTests(APITestCase):
    """站内通知接收人与 API 列表。"""

    tenant: Tenant
    location: Location
    resource: Resource
    service: Service
    time_slot: TimeSlot

    def setUp(self):
        """准备租户、预约与客户 JWT。"""
        cache.clear()
        sms_sent_message_clear()
        from notifications.services.messaging import broker_message_clear

        broker_message_clear()
        self.tenant = Tenant.objects.create(
            slug="acme",
            name="Acme Corp",
            timezone="Asia/Shanghai",
        )
        self.location = Location.objects.create(tenant=self.tenant, name="Main Studio")
        self.resource = Resource.objects.create(
            tenant=self.tenant,
            location=self.location,
            name="Alice",
        )
        self.service = Service.objects.create(
            tenant=self.tenant,
            location=self.location,
            name="Haircut",
            duration_minutes=60,
        )
        self.service.resources.add(self.resource)

        tenant_tz = ZoneInfo("Asia/Shanghai")
        slot_start = datetime(2026, 8, 1, 9, 0, tzinfo=tenant_tz).astimezone(UTC)
        slot_end = datetime(2026, 8, 1, 10, 0, tzinfo=tenant_tz).astimezone(UTC)
        self.time_slot = TimeSlot.objects.create(
            tenant=self.tenant,
            location=self.location,
            resource=self.resource,
            start=slot_start,
            end=slot_end,
            capacity=3,
            status=TimeSlotStatus.OPEN,
        )
        self.other_slot = TimeSlot.objects.create(
            tenant=self.tenant,
            location=self.location,
            resource=self.resource,
            start=slot_start + timedelta(days=1),
            end=slot_end + timedelta(days=1),
            capacity=3,
            status=TimeSlotStatus.OPEN,
        )
        self.reschedule_slot = TimeSlot.objects.create(
            tenant=self.tenant,
            location=self.location,
            resource=self.resource,
            start=slot_start + timedelta(days=2),
            end=slot_end + timedelta(days=2),
            capacity=3,
            status=TimeSlotStatus.OPEN,
        )

        self.phone = "13900139000"
        self._login_customer()

    def _login_customer(self) -> None:
        """发送 OTP 并登录，设置 Bearer 凭据。"""
        self.client.post(
            "/api/v1/auth/customer/verification-codes/",
            {"phone": self.phone},
            format="json",
        )
        code = sms_sent_message_list()[-1]["code"]
        login = self.client.post(
            "/api/v1/auth/customer/sessions/",
            {"phone": self.phone, "code": code, "tenant_slug": "acme"},
            format="json",
        )
        from tests.support import api_data

        access = api_data(login)["access"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
        self.customer_user = User.objects.get(customer_profile__phone=self.phone)
        self.customer = TenantCustomer.objects.get(tenant=self.tenant, user=self.customer_user)

    def _consume_pending_outbox(self) -> None:
        """发布并消费所有 Outbox 事件（测试辅助）。"""
        from notifications.services.consume import notifications_outbox_event_consume
        from notifications.services.messaging import broker_message_list
        from notifications.tasks import notifications_publish_outbox_events

        notifications_publish_outbox_events()
        for message in broker_message_list():
            notifications_outbox_event_consume(
                event_id=message["event_id"],
                event_type=message["event_type"],
                payload=message["payload"],
            )

    def test_confirm_cancel_reschedule_notify_customer(self):
        """确认、取消、改期通知发送给预约客户。"""
        from notifications.models import Notification

        booking = scheduling_booking_create(
            tenant=self.tenant,
            customer=self.customer,
            idempotency_key="lifecycle-1",
            service_id=self.service.id,
            party_size=1,
            time_slot_id=self.time_slot.id,
        )
        self._consume_pending_outbox()
        self.assertTrue(
            Notification.objects.filter(
                recipient=self.customer_user,
                notification_type="booking.confirmed",
            ).exists()
        )

        pending = Booking.objects.create(
            tenant=self.tenant,
            customer=self.customer,
            time_slot=self.other_slot,
            service=self.service,
            status=BookingStatus.PENDING,
            party_size=1,
            idempotency_key="pending-1",
        )
        scheduling_booking_confirm(booking=pending)
        self._consume_pending_outbox()
        self.assertTrue(
            Notification.objects.filter(
                recipient=self.customer_user,
                notification_type="booking.confirmed",
                booking=pending,
            ).exists()
        )

        scheduling_booking_cancel(
            booking=booking,
            actor=BookingCancelActor.CUSTOMER,
        )
        self._consume_pending_outbox()
        self.assertTrue(
            Notification.objects.filter(
                recipient=self.customer_user,
                notification_type="booking.cancelled",
                booking=booking,
            ).exists()
        )

        reschedule_source = scheduling_booking_create(
            tenant=self.tenant,
            customer=self.customer,
            idempotency_key="resched-src",
            service_id=self.service.id,
            party_size=1,
            time_slot_id=self.time_slot.id,
        )
        new_booking = scheduling_booking_reschedule(
            booking=reschedule_source,
            new_time_slot_id=self.reschedule_slot.id,
            idempotency_key="resched-new",
        )
        self._consume_pending_outbox()
        self.assertTrue(
            Notification.objects.filter(
                recipient=self.customer_user,
                notification_type="booking.rescheduled",
                booking=new_booking,
            ).exists()
        )

    def test_customer_lists_notifications_via_api(self):
        """客户可通过 API 列出本人的站内通知。"""
        scheduling_booking_create(
            tenant=self.tenant,
            customer=self.customer,
            idempotency_key="api-list",
            service_id=self.service.id,
            party_size=1,
            time_slot_id=self.time_slot.id,
        )
        self._consume_pending_outbox()

        response = self.client.get("/api/v1/acme/notifications/")
        from tests.support import api_data

        items = api_data(response)
        self.assertGreaterEqual(len(items), 1)
        self.assertEqual(items[0]["notification_type"], "booking.confirmed")


@override_settings(CELERY_TASK_ALWAYS_EAGER=True)
class ReminderAndSmsTests(TestCase):
    """预约提醒与 Mock 短信可观察性。"""

    def setUp(self):
        """准备即将开始的已确认预约。"""
        cache.clear()
        sms_sent_message_clear()
        from notifications.services.messaging import broker_message_clear

        broker_message_clear()
        self.tenant = Tenant.objects.create(
            slug="remind",
            name="Remind Tenant",
            timezone="Asia/Shanghai",
        )
        self.location = Location.objects.create(tenant=self.tenant, name="Studio")
        self.resource = Resource.objects.create(
            tenant=self.tenant,
            location=self.location,
            name="Bob",
        )
        self.service = Service.objects.create(
            tenant=self.tenant,
            location=self.location,
            name="Cut",
            duration_minutes=60,
        )
        self.service.resources.add(self.resource)

        self.user = User.objects.create_user(username="reminder-user")
        CustomerProfile.objects.create(user=self.user, phone="13900138888")
        self.customer = TenantCustomer.objects.create(tenant=self.tenant, user=self.user)

        from scheduling.models import TenantBookingSettings

        TenantBookingSettings.objects.create(
            tenant=self.tenant,
            reminder_minutes_before=60,
        )

    def test_reminder_task_sends_in_app_and_sms_before_appointment(self):
        """提醒任务在预约开始前发送站内通知与短信。"""
        from unittest.mock import patch

        from notifications.models import Notification
        from notifications.services.consume import notifications_outbox_event_consume
        from notifications.services.messaging import broker_message_list
        from notifications.tasks import (
            notifications_publish_outbox_events,
            notifications_send_appointment_reminders,
        )

        now = timezone.now()
        slot_start = now + timedelta(minutes=45)
        slot_end = slot_start + timedelta(hours=1)
        time_slot = TimeSlot.objects.create(
            tenant=self.tenant,
            location=self.location,
            resource=self.resource,
            start=slot_start,
            end=slot_end,
            capacity=1,
            status=TimeSlotStatus.OPEN,
        )
        booking = Booking.objects.create(
            tenant=self.tenant,
            customer=self.customer,
            time_slot=time_slot,
            service=self.service,
            status=BookingStatus.CONFIRMED,
            party_size=1,
            idempotency_key="reminder-booking",
        )

        with patch("django.utils.timezone.now", return_value=now):
            notifications_send_appointment_reminders()
            notifications_publish_outbox_events()
            for message in broker_message_list():
                notifications_outbox_event_consume(
                    event_id=message["event_id"],
                    event_type=message["event_type"],
                    payload=message["payload"],
                )

        self.assertTrue(
            Notification.objects.filter(
                recipient=self.user,
                notification_type="booking.reminder",
                booking=booking,
            ).exists()
        )
        sms_messages = [
            msg for msg in sms_sent_message_list() if msg.get("kind") == "booking_notification"
        ]
        self.assertEqual(len(sms_messages), 1)
        self.assertEqual(sms_messages[0]["phone"], "13900138888")
