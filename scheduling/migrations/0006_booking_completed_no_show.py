from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("scheduling", "0005_booking_lifecycle"),
    ]

    operations = [
        migrations.AlterField(
            model_name="booking",
            name="status",
            field=models.CharField(
                choices=[
                    ("pending", "待确认"),
                    ("confirmed", "已确认"),
                    ("started", "已开始"),
                    ("completed", "已完成"),
                    ("no_show", "爽约"),
                    ("cancelled", "已取消"),
                    ("rescheduled", "已改期"),
                    ("expired", "已过期"),
                    ("rejected", "已拒绝"),
                ],
                max_length=16,
            ),
        ),
    ]
