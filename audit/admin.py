from django.contrib import admin

from audit.models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    """审计日志只读管理界面。"""

    list_display = (
        "id",
        "tenant",
        "action",
        "target_type",
        "target_id",
        "operator",
        "request_id",
        "created_at",
    )
    list_filter = ("action", "target_type", "tenant")
    search_fields = ("request_id", "target_id")
    readonly_fields = (
        "tenant",
        "operator",
        "request_id",
        "ip_address",
        "action",
        "target_type",
        "target_id",
        "before_value",
        "after_value",
        "details",
        "created_at",
    )

    def has_add_permission(self, request) -> bool:
        """禁止通过 Admin 新增审计记录。

        Args:
            request: Django 请求对象。

        Returns:
            bool: 始终 ``False``。
        """
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        """禁止通过 Admin 修改审计记录。

        Args:
            request: Django 请求对象。
            obj: 可选对象实例。

        Returns:
            bool: 始终 ``False``。
        """
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        """禁止通过 Admin 删除审计记录。

        Args:
            request: Django 请求对象。
            obj: 可选对象实例。

        Returns:
            bool: 始终 ``False``。
        """
        return False
