"""长期订阅 RabbitMQ Outbox exchange 的 Django management command。"""

from django.core.management.base import BaseCommand

from notifications.services.consumer import outbox_consumer_run


class Command(BaseCommand):
    """启动 Outbox RabbitMQ 消费者进程。"""

    help = "Subscribe to appointly.outbox and consume outbox events."

    def handle(self, *args, **options) -> None:
        """启动长期运行的 Outbox 消费者。

        Args:
            *args: Django 传入的位置参数。
            **options: Django 传入的选项。
        """
        self.stdout.write("Starting outbox consumer...")
        outbox_consumer_run()
