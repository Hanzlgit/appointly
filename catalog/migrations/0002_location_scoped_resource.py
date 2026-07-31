import django.db.models.deletion
from django.db import migrations, models


def delete_all_resources(apps, schema_editor):
    """硬切：删除全部旧资源数据后再应用新 schema。"""
    Resource = apps.get_model("catalog", "Resource")
    Resource.objects.all().delete()


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(delete_all_resources, migrations.RunPython.noop),
        migrations.RemoveConstraint(
            model_name="resource",
            name="unique_tenant_resource_name",
        ),
        migrations.RemoveField(
            model_name="resource",
            name="locations",
        ),
        migrations.RemoveField(
            model_name="resource",
            name="resource_type",
        ),
        migrations.RemoveField(
            model_name="resource",
            name="staff_user",
        ),
        migrations.AddField(
            model_name="resource",
            name="location",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="resources",
                to="catalog.location",
            ),
            preserve_default=False,
        ),
        migrations.AddConstraint(
            model_name="resource",
            constraint=models.UniqueConstraint(
                fields=("tenant", "location", "name"),
                name="unique_tenant_location_resource_name",
            ),
        ),
    ]
