from django.apps import AppConfig


class NotificationsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "notifications"
    verbose_name = "通知"

    def ready(self) -> None:
        """应用启动钩子。"""
        import notifications.admin  # noqa: F401
