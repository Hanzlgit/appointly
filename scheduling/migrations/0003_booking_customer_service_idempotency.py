import django.db.models.deletion
from django.db import migrations, models


def booking_set_defaults(apps, schema_editor):
    """为既有预约行填充占位客户、服务与幂等键。"""
    Booking = apps.get_model("scheduling", "Booking")
    TenantCustomer = apps.get_model("tenants", "TenantCustomer")
    Service = apps.get_model("catalog", "Service")

    for booking in Booking.objects.select_related("tenant", "time_slot").iterator():
        customer = TenantCustomer.objects.filter(tenant_id=booking.tenant_id).first()
        if customer is None:
            continue
        service = Service.objects.filter(tenant_id=booking.tenant_id).first()
        if service is None:
            continue
        booking.customer_id = customer.id
        booking.service_id = service.id
        booking.idempotency_key = f"legacy-{booking.pk}"
        booking.save(update_fields=["customer_id", "service_id", "idempotency_key"])


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0001_initial"),
        ("scheduling", "0002_booking_party_size"),
        ("tenants", "0003_customer_auth"),
    ]

    operations = [
        migrations.AddField(
            model_name="booking",
            name="customer",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="bookings",
                to="tenants.tenantcustomer",
            ),
        ),
        migrations.AddField(
            model_name="booking",
            name="service",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="bookings",
                to="catalog.service",
            ),
        ),
        migrations.AddField(
            model_name="booking",
            name="idempotency_key",
            field=models.CharField(default="legacy", max_length=128),
            preserve_default=False,
        ),
        migrations.RunPython(booking_set_defaults, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="booking",
            name="customer",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="bookings",
                to="tenants.tenantcustomer",
            ),
        ),
        migrations.AlterField(
            model_name="booking",
            name="service",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="bookings",
                to="catalog.service",
            ),
        ),
        migrations.AddConstraint(
            model_name="booking",
            constraint=models.UniqueConstraint(
                fields=("tenant", "customer", "idempotency_key"),
                name="unique_booking_idempotency_per_customer",
            ),
        ),
    ]
