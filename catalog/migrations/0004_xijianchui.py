import django.db.models.deletion
from django.db import migrations, models


def _table_exists(cursor, table: str) -> bool:
    """检查表是否存在。"""
    cursor.execute(
        """
        SELECT COUNT(*) FROM information_schema.TABLES
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s
        """,
        [table],
    )
    return cursor.fetchone()[0] > 0


def _column_exists(cursor, table: str, column: str) -> bool:
    """检查列是否存在。"""
    cursor.execute(
        """
        SELECT COUNT(*) FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s AND COLUMN_NAME = %s
        """,
        [table, column],
    )
    return cursor.fetchone()[0] > 0


def _constraint_exists(cursor, table: str, name: str) -> bool:
    """检查约束/索引是否存在。"""
    cursor.execute(
        """
        SELECT COUNT(*) FROM information_schema.TABLE_CONSTRAINTS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s AND CONSTRAINT_NAME = %s
        """,
        [table, name],
    )
    return cursor.fetchone()[0] > 0


def _drop_constraint_if_exists(cursor, table: str, name: str) -> None:
    """安全删除约束。"""
    if _constraint_exists(cursor, table, name):
        cursor.execute(f"ALTER TABLE `{table}` DROP INDEX `{name}`")


def _drop_column_if_exists(cursor, table: str, column: str) -> None:
    """安全删除列。"""
    if _column_exists(cursor, table, column):
        cursor.execute(f"ALTER TABLE `{table}` DROP COLUMN `{column}`")


def apply_xijianchui_schema(apps, schema_editor):
    """幂等应用洗剪吹 schema 变更。"""
    connection = schema_editor.connection
    with connection.cursor() as cursor:
        cursor.execute("SET FOREIGN_KEY_CHECKS = 0")

        if _table_exists(cursor, "catalog_resource") and not _table_exists(cursor, "catalog_stylist"):
            cursor.execute("RENAME TABLE `catalog_resource` TO `catalog_stylist`")

        _drop_constraint_if_exists(cursor, "catalog_location", "unique_tenant_location_name")
        _drop_column_if_exists(cursor, "catalog_location", "tenant_id")
        if not _constraint_exists(cursor, "catalog_location", "unique_location_name"):
            cursor.execute(
                "ALTER TABLE `catalog_location` ADD CONSTRAINT `unique_location_name` UNIQUE (`name`)"
            )

        if _table_exists(cursor, "catalog_stylist"):
            _drop_constraint_if_exists(cursor, "catalog_stylist", "unique_tenant_location_resource_name")
            _drop_column_if_exists(cursor, "catalog_stylist", "tenant_id")
            if not _column_exists(cursor, "catalog_stylist", "queue_status"):
                cursor.execute(
                    "ALTER TABLE `catalog_stylist` ADD COLUMN `queue_status` varchar(16) NOT NULL DEFAULT 'open'"
                )
            if not _column_exists(cursor, "catalog_stylist", "ticket_prefix"):
                cursor.execute(
                    "ALTER TABLE `catalog_stylist` ADD COLUMN `ticket_prefix` varchar(8) NOT NULL DEFAULT ''"
                )
            if not _constraint_exists(cursor, "catalog_stylist", "unique_location_stylist_name"):
                cursor.execute(
                    "ALTER TABLE `catalog_stylist` ADD CONSTRAINT `unique_location_stylist_name` UNIQUE (`location_id`, `name`)"
                )

        if _table_exists(cursor, "catalog_catalogbusinessreference"):
            _drop_column_if_exists(cursor, "catalog_catalogbusinessreference", "resource_id")
            _drop_column_if_exists(cursor, "catalog_catalogbusinessreference", "tenant_id")
            if not _column_exists(cursor, "catalog_catalogbusinessreference", "stylist_id"):
                cursor.execute(
                    "ALTER TABLE `catalog_catalogbusinessreference` ADD COLUMN `stylist_id` bigint NULL"
                )

        if _table_exists(cursor, "catalog_service"):
            if _table_exists(cursor, "catalog_service_resources"):
                cursor.execute("DROP TABLE IF EXISTS `catalog_service_resources`")
            _drop_constraint_if_exists(cursor, "catalog_service", "unique_tenant_location_service_name")
            _drop_column_if_exists(cursor, "catalog_service", "location_id")
            _drop_column_if_exists(cursor, "catalog_service", "tenant_id")
            if not _column_exists(cursor, "catalog_service", "stylist_id"):
                cursor.execute("DELETE FROM `catalog_service`")
                cursor.execute(
                    "ALTER TABLE `catalog_service` ADD COLUMN `stylist_id` bigint NOT NULL"
                )
                cursor.execute(
                    "ALTER TABLE `catalog_service` ADD CONSTRAINT `catalog_service_stylist_id_fk` "
                    "FOREIGN KEY (`stylist_id`) REFERENCES `catalog_stylist` (`id`)"
                )
            if not _constraint_exists(cursor, "catalog_service", "unique_stylist_service_name"):
                cursor.execute(
                    "ALTER TABLE `catalog_service` ADD CONSTRAINT `unique_stylist_service_name` UNIQUE (`stylist_id`, `name`)"
                )

        cursor.execute("SET FOREIGN_KEY_CHECKS = 1")


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0003_location_scoped_service"),
        ("scheduling", "0009_remove_booking_party_size"),
    ]

    operations = [
        migrations.RunPython(apply_xijianchui_schema, migrations.RunPython.noop),
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.RemoveConstraint(
                    model_name="location",
                    name="unique_tenant_location_name",
                ),
                migrations.RemoveField(model_name="location", name="tenant"),
                migrations.AddConstraint(
                    model_name="location",
                    constraint=models.UniqueConstraint(fields=("name",), name="unique_location_name"),
                ),
                migrations.RenameModel(old_name="Resource", new_name="Stylist"),
                migrations.RemoveConstraint(
                    model_name="stylist",
                    name="unique_tenant_location_resource_name",
                ),
                migrations.RemoveField(model_name="stylist", name="tenant"),
                migrations.AddField(
                    model_name="stylist",
                    name="queue_status",
                    field=models.CharField(
                        choices=[("open", "开放"), ("paused", "暂停"), ("closed", "关闭")],
                        default="open",
                        max_length=16,
                    ),
                ),
                migrations.AddField(
                    model_name="stylist",
                    name="ticket_prefix",
                    field=models.CharField(blank=True, default="", max_length=8),
                ),
                migrations.AddConstraint(
                    model_name="stylist",
                    constraint=models.UniqueConstraint(
                        fields=("location", "name"),
                        name="unique_location_stylist_name",
                    ),
                ),
                migrations.AlterModelOptions(
                    name="stylist",
                    options={
                        "ordering": ["name"],
                        "verbose_name": "理发师",
                        "verbose_name_plural": "理发师",
                    },
                ),
                migrations.RemoveField(model_name="catalogbusinessreference", name="resource"),
                migrations.RemoveField(model_name="catalogbusinessreference", name="tenant"),
                migrations.AddField(
                    model_name="catalogbusinessreference",
                    name="stylist",
                    field=models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="business_references",
                        to="catalog.stylist",
                    ),
                ),
                migrations.RemoveField(model_name="service", name="resources"),
                migrations.RemoveConstraint(
                    model_name="service",
                    name="unique_tenant_location_service_name",
                ),
                migrations.RemoveField(model_name="service", name="location"),
                migrations.RemoveField(model_name="service", name="tenant"),
                migrations.AddField(
                    model_name="service",
                    name="stylist",
                    field=models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="services",
                        to="catalog.stylist",
                    ),
                    preserve_default=False,
                ),
                migrations.AddConstraint(
                    model_name="service",
                    constraint=models.UniqueConstraint(
                        fields=("stylist", "name"),
                        name="unique_stylist_service_name",
                    ),
                ),
            ],
        ),
    ]
