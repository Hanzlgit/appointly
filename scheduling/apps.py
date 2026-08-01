from django.apps import AppConfig


class SchedulingConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "scheduling"
    verbose_name = "排班与时段"

    # scheduling 已退役；保留 AppConfig 供历史迁移加载，不注册信号。
