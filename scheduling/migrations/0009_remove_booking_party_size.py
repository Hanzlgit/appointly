from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("scheduling", "0008_schedule_rule_slot_interval"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="booking",
            name="party_size",
        ),
    ]
