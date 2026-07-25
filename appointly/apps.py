from django.apps import AppConfig


class AppointlyConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "appointly"

    def ready(self) -> None:
        from config.celery import app as celery_app

        _ = celery_app
