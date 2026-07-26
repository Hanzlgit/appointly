from django.apps import AppConfig


class AuditConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "audit"
    verbose_name = "审计"

    def ready(self) -> None:
        """应用启动钩子。"""
        import audit.admin  # noqa: F401
