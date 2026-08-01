from django.apps import AppConfig


class QueuingConfig(AppConfig):
    """排队叫号域模块。"""

    default_auto_field = "django.db.models.BigAutoField"
    name = "queuing"
    verbose_name = "排队叫号"
