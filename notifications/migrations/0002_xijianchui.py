import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("notifications", "0001_outbox_notifications"),
        ("queuing", "0001_initial"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="notification",
            name="booking",
        ),
        migrations.RemoveField(
            model_name="notification",
            name="tenant",
        ),
        migrations.RemoveField(
            model_name="outboxevent",
            name="tenant",
        ),
        migrations.AddField(
            model_name="notification",
            name="queue_ticket",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="notifications",
                to="queuing.queueticket",
            ),
        ),
    ]
