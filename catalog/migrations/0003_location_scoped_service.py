import django.db.models.deletion
from django.db import migrations, models


def delete_all_services(apps, schema_editor):
    """硬切：删除全部旧服务数据后再应用新 schema。"""
    Service = apps.get_model("catalog", "Service")
    Service.objects.all().delete()


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0002_location_scoped_resource"),
    ]

    operations = [
        migrations.RunPython(delete_all_services, migrations.RunPython.noop),
        migrations.RemoveConstraint(
            model_name="service",
            name="unique_tenant_service_name",
        ),
        migrations.AddField(
            model_name="service",
            name="location",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="services",
                to="catalog.location",
            ),
            preserve_default=False,
        ),
        migrations.AddConstraint(
            model_name="service",
            constraint=models.UniqueConstraint(
                fields=("tenant", "location", "name"),
                name="unique_tenant_location_service_name",
            ),
        ),
    ]
