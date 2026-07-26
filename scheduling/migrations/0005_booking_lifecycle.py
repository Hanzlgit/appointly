import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("scheduling", "0004_booking_rules"),
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
                    ("cancelled", "已取消"),
                    ("rescheduled", "已改期"),
                    ("expired", "已过期"),
                    ("rejected", "已拒绝"),
                ],
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name="booking",
            name="archived_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="booking",
            name="cancel_actor",
            field=models.CharField(
                blank=True,
                choices=[
                    ("customer", "客户"),
                    ("admin", "管理员"),
                    ("system", "系统"),
                ],
                max_length=16,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="booking",
            name="cancel_reason",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AddField(
            model_name="booking",
            name="cancel_operator",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="cancelled_bookings",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="booking",
            name="contact_name",
            field=models.CharField(blank=True, default="", max_length=128),
        ),
        migrations.AddField(
            model_name="booking",
            name="contact_phone",
            field=models.CharField(blank=True, default="", max_length=32),
        ),
        migrations.AddField(
            model_name="booking",
            name="rescheduled_from",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="rescheduled_to_booking",
                to="scheduling.booking",
            ),
        ),
        migrations.AddField(
            model_name="booking",
            name="rescheduled_to",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="rescheduled_from_booking",
                to="scheduling.booking",
            ),
        ),
    ]
