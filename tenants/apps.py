from django.apps import AppConfig


class TenantsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "tenants"
    verbose_name = "租户管理"

    def ready(self) -> None:
        import tenants.admin  # noqa: F401
