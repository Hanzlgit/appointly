from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("scheduling", "0007_outbox_notifications"),
    ]

    operations = [
        migrations.AddField(
            model_name="schedulerule",
            name="slot_interval_minutes",
            field=models.PositiveSmallIntegerField(default=30),
        ),
    ]
