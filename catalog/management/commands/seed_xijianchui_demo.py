"""写入演示门店、理发师与服务数据。"""

from django.core.management.base import BaseCommand

from catalog.models import Location, Service, Stylist, StylistQueueStatus


class Command(BaseCommand):
    """初始化洗剪吹演示数据。"""

    help = "创建演示门店、理发师与服务项目"

    def handle(self, *args, **options):
        """执行种子数据写入。

        Args:
            *args: 位置参数。
            **options: 命令选项。
        """
        location, _ = Location.objects.get_or_create(
            name="万达店",
            defaults={"address": "万达广场 1F", "is_active": True},
        )
        stylist_a, _ = Stylist.objects.get_or_create(
            location=location,
            name="A剪发师",
            defaults={
                "ticket_prefix": "A",
                "queue_status": StylistQueueStatus.OPEN,
                "is_active": True,
            },
        )
        stylist_b, _ = Stylist.objects.get_or_create(
            location=location,
            name="B剪发师",
            defaults={
                "ticket_prefix": "B",
                "queue_status": StylistQueueStatus.OPEN,
                "is_active": True,
            },
        )
        services_a = [
            ("男士洗剪吹", 45, 6800),
            ("女士洗剪吹", 60, 9800),
            ("儿童单剪", 20, 3000),
            ("老人单剪", 25, 2500),
        ]
        for name, duration, price in services_a:
            Service.objects.get_or_create(
                stylist=stylist_a,
                name=name,
                defaults={
                    "duration_minutes": duration,
                    "price_cents": price,
                    "is_active": True,
                },
            )
        services_b = [
            ("男士洗剪吹", 45, 5800),
            ("老人单剪", 25, 2500),
        ]
        for name, duration, price in services_b:
            Service.objects.get_or_create(
                stylist=stylist_b,
                name=name,
                defaults={
                    "duration_minutes": duration,
                    "price_cents": price,
                    "is_active": True,
                },
            )
        self.stdout.write(self.style.SUCCESS("演示数据已就绪：万达店 / A剪发师 / B剪发师"))
