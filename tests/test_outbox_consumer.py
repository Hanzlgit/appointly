"""Outbox 消费者 publish→consume 链路测试。"""

from accounts.models import CustomerProfile
from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from notifications.models import Notification, OutboxEvent
from notifications.services.messaging import broker_message_clear
from notifications.tasks import notifications_publish_outbox_events
from tenants.models import Tenant


@override_settings(CELERY_TASK_ALWAYS_EAGER=True)
class OutboxConsumerPublishConsumeTests(TestCase):
    """发布到 Mock 代理后由消费者处理产生副作用。"""

    def setUp(self):
        """准备未发布 Outbox 事件与接收用户。"""
        broker_message_clear()
        self.tenant = Tenant.objects.create(slug="consumer", name="Consumer Tenant")
        self.user = User.objects.create_user(username="consumer-user")
        CustomerProfile.objects.create(user=self.user, phone="13900137777")
        self.event = OutboxEvent.objects.create(
            tenant=self.tenant,
            event_type="booking.confirmed",
            aggregate_type="booking",
            aggregate_id=7,
            payload={
                "tenant_id": self.tenant.id,
                "booking_id": 7,
                "recipient_user_id": self.user.id,
                "title": "预约已确认",
                "body": "您的预约已确认。",
                "phone": "13900137777",
            },
        )

    def test_publish_then_consumer_creates_notification(self):
        """发布任务投递消息后，消费者处理产生一条站内通知。"""
        from notifications.services.consumer import outbox_consumer_process_mock_pending

        notifications_publish_outbox_events()
        processed_count = outbox_consumer_process_mock_pending()

        self.assertEqual(processed_count, 1)
        self.assertEqual(
            Notification.objects.filter(source_event_id=self.event.event_id).count(),
            1,
        )

    def test_duplicate_consumer_delivery_is_idempotent(self):
        """消费者重复处理同一 event_id 只产生一条站内通知。"""
        from notifications.services.consumer import outbox_consumer_message_handle

        message = {
            "event_id": str(self.event.event_id),
            "event_type": self.event.event_type,
            "payload": self.event.payload,
        }
        outbox_consumer_message_handle(message=message)
        outbox_consumer_message_handle(message=message)

        self.assertEqual(
            Notification.objects.filter(source_event_id=self.event.event_id).count(),
            1,
        )


@override_settings(OUTBOX_MESSAGE_BROKER="mock", CELERY_TASK_ALWAYS_EAGER=True)
class OutboxConsumerRunTests(TestCase):
    """RabbitMQ 长期消费者入口约束。"""

    def test_run_rejects_non_rabbitmq_broker(self):
        """Mock 配置下不可启动 RabbitMQ 长期消费者。"""
        from notifications.services.consumer import outbox_consumer_run

        with self.assertRaisesMessage(ValueError, "OUTBOX_MESSAGE_BROKER=rabbitmq"):
            outbox_consumer_run()


class OutboxConsumerCommandTests(TestCase):
    """Management command 接线。"""

    def test_consume_outbox_events_command_invokes_consumer_run(self):
        """consume_outbox_events 命令应调用 outbox_consumer_run。"""
        from io import StringIO
        from unittest.mock import patch

        from django.core.management import call_command

        stdout = StringIO()
        with patch(
            "notifications.management.commands.consume_outbox_events.outbox_consumer_run",
        ) as mock_run:
            call_command("consume_outbox_events", stdout=stdout)

        mock_run.assert_called_once_with()
