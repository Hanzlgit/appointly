from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("scheduling", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="booking",
            name="party_size",
            field=models.PositiveIntegerField(default=1),
        ),
    ]
