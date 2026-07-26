from django.apps import AppConfig


class CatalogConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "catalog"
    verbose_name = "业务目录"

    def ready(self) -> None:
        """应用启动钩子。"""
        import catalog.admin  # noqa: F401
