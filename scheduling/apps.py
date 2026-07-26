from django.apps import AppConfig


class SchedulingConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "scheduling"
    verbose_name = "排班与时段"

    def ready(self) -> None:
        """注册排班应用信号处理器。"""
        import scheduling.signals  # noqa: F401
