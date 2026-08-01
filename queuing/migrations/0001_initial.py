import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("catalog", "0004_xijianchui"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="QueueTicket",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("ticket_number", models.PositiveIntegerField()),
                ("queue_date", models.DateField()),
                ("position", models.PositiveIntegerField()),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("waiting", "排队中"),
                            ("called", "已叫号"),
                            ("serving", "服务中"),
                            ("completed", "已完成"),
                            ("cancelled", "已取消"),
                        ],
                        max_length=16,
                    ),
                ),
                ("idempotency_key", models.CharField(max_length=128)),
                ("called_at", models.DateTimeField(blank=True, null=True)),
                ("serving_started_at", models.DateTimeField(blank=True, null=True)),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
                ("cancelled_at", models.DateTimeField(blank=True, null=True)),
                ("cancel_reason", models.TextField(blank=True, default="")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "customer",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="queue_tickets",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "location",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="queue_tickets",
                        to="catalog.location",
                    ),
                ),
                (
                    "service",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="queue_tickets",
                        to="catalog.service",
                    ),
                ),
                (
                    "stylist",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="queue_tickets",
                        to="catalog.stylist",
                    ),
                ),
            ],
            options={
                "verbose_name": "排队号",
                "verbose_name_plural": "排队号",
                "ordering": ["position", "created_at"],
            },
        ),
        migrations.AddConstraint(
            model_name="queueticket",
            constraint=models.UniqueConstraint(
                fields=("stylist", "queue_date", "ticket_number"),
                name="unique_stylist_date_ticket_number",
            ),
        ),
        migrations.AddConstraint(
            model_name="queueticket",
            constraint=models.UniqueConstraint(
                fields=("customer", "idempotency_key"),
                name="unique_queue_ticket_idempotency_per_customer",
            ),
        ),
        migrations.AddConstraint(
            model_name="queueticket",
            constraint=models.UniqueConstraint(
                condition=models.Q(
                    ("status__in", ["waiting", "called", "serving"])
                ),
                fields=("customer",),
                name="unique_active_queue_ticket_per_customer",
            ),
        ),
    ]
