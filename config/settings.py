import os
from datetime import timedelta
from pathlib import Path
from urllib.parse import urlparse

from django.core.management.utils import get_random_secret_key

BASE_DIR = Path(__file__).resolve().parent.parent


def _load_dotenv(path: Path) -> None:
    """从 ``.env`` 文件加载环境变量（不覆盖已有值）。

    Args:
        path (Path): ``.env`` 文件路径。
    """
    if not path.exists():
        return

    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv(BASE_DIR / ".env")


def _env_bool(name: str, default: bool = False) -> bool:
    """读取布尔型环境变量。

    Args:
        name (str): 环境变量名。
        default (bool): 未设置时的默认值。

    Returns:
        bool: 解析后的布尔值。
    """
    value = os.environ.get(name)
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


def _database_from_url(url: str) -> dict:
    """将数据库 URL 解析为 Django ``DATABASES`` 配置项。

    Args:
        url (str): 形如 ``mysql://user:pass@host:port/db`` 的连接 URL。

    Returns:
        dict: Django 数据库配置字典。
    """
    parsed = urlparse(url)
    return {
        "ENGINE": "django.db.backends.mysql",
        "NAME": parsed.path.lstrip("/"),
        "USER": parsed.username or "",
        "PASSWORD": parsed.password or "",
        "HOST": parsed.hostname or "127.0.0.1",
        "PORT": str(parsed.port or 3306),
        "OPTIONS": {
            "charset": "utf8mb4",
            "init_command": "SET sql_mode='STRICT_TRANS_TABLES'",
        },
    }


SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", get_random_secret_key())
DEBUG = _env_bool("DJANGO_DEBUG", default=False)
ALLOWED_HOSTS = [
    host.strip()
    for host in os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")
    if host.strip()
]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "corsheaders",
    "rest_framework",
    "rest_framework_simplejwt",
    "rest_framework_simplejwt.token_blacklist",
    "drf_spectacular",
    "appointly",
    "accounts.apps.AccountsConfig",
    "tenants.apps.TenantsConfig",
    "catalog.apps.CatalogConfig",
    "scheduling.apps.SchedulingConfig",
    "notifications.apps.NotificationsConfig",
    "audit.apps.AuditConfig",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "appointly.api.middleware.RequestIdMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

DATABASES = {
    "default": _database_from_url(
        os.environ.get("DATABASE_URL", "mysql://appointly:appointly@127.0.0.1:3306/appointly")
    )
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "zh-hans"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


def _env_int(name: str, default: int) -> int:
    """读取整型环境变量。

    Args:
        name (str): 环境变量名。
        default (int): 未设置时的默认值。

    Returns:
        int: 解析后的整数值。
    """
    value = os.environ.get(name)
    if value is None:
        return default
    return int(value)


JWT_ACCESS_TOKEN_LIFETIME = timedelta(minutes=_env_int("JWT_ACCESS_TOKEN_LIFETIME_MINUTES", 15))
JWT_REFRESH_TOKEN_LIFETIME = timedelta(days=_env_int("JWT_REFRESH_TOKEN_LIFETIME_DAYS", 7))

REST_FRAMEWORK = {
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ],
    "EXCEPTION_HANDLER": "appointly.api.exceptions.api_exception_handler",
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": JWT_ACCESS_TOKEN_LIFETIME,
    "REFRESH_TOKEN_LIFETIME": JWT_REFRESH_TOKEN_LIFETIME,
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
}

SPECTACULAR_SETTINGS = {
    "TITLE": "Appointly API",
    "DESCRIPTION": "通用多租户预约 SaaS",
    "VERSION": "0.1.0",
}

REDIS_URL = os.environ.get("REDIS_URL", "redis://127.0.0.1:16379/0")

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": REDIS_URL,
    }
}

SMS_ADAPTER = os.environ.get("SMS_ADAPTER", "mock")
OUTBOX_MESSAGE_BROKER = os.environ.get("OUTBOX_MESSAGE_BROKER", "mock")
OTP_CODE_LENGTH = _env_int("OTP_CODE_LENGTH", 6)
OTP_TTL_SECONDS = _env_int("OTP_TTL_SECONDS", 300)
OTP_SEND_INTERVAL_SECONDS = _env_int("OTP_SEND_INTERVAL_SECONDS", 60)
OTP_DAILY_SEND_LIMIT = _env_int("OTP_DAILY_SEND_LIMIT", 10)
OTP_DAILY_COUNTER_TTL_SECONDS = _env_int("OTP_DAILY_COUNTER_TTL_SECONDS", 60 * 60 * 26)
OTP_MAX_VERIFY_FAILURES = _env_int("OTP_MAX_VERIFY_FAILURES", 5)
OTP_LOCK_SECONDS = _env_int("OTP_LOCK_SECONDS", 900)

CELERY_BROKER_URL = os.environ.get(
    "CELERY_BROKER_URL", "amqp://appointly:appointly@127.0.0.1:25672//"
)
CELERY_RESULT_BACKEND = os.environ.get("CELERY_RESULT_BACKEND", "redis://127.0.0.1:16379/1")
CELERY_TASK_ALWAYS_EAGER = _env_bool("CELERY_TASK_ALWAYS_EAGER", default=False)
CELERY_TASK_EAGER_PROPAGATES = True
CELERY_TIMEZONE = TIME_ZONE
CELERY_BEAT_SCHEDULE = {
    "scheduling-generate-timeslots": {
        "task": "scheduling.generate_timeslots_for_all_tenants",
        "schedule": 3600.0,
    },
    "scheduling-expire-pending-bookings": {
        "task": "scheduling.expire_pending_bookings",
        "schedule": 60.0,
    },
    "notifications-publish-outbox": {
        "task": "notifications.publish_outbox_events",
        "schedule": 30.0,
    },
    "notifications-send-reminders": {
        "task": "notifications.send_appointment_reminders",
        "schedule": 300.0,
    },
    "audit-purge-expired-logs": {
        "task": "audit.purge_expired_logs",
        "schedule": 86400.0,
    },
}

SENTRY_DSN = os.environ.get("SENTRY_DSN", "")
if SENTRY_DSN:
    import sentry_sdk

    sentry_sdk.init(
        dsn=SENTRY_DSN,
        traces_sample_rate=0.1,
        send_default_pii=False,
    )

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "json": {
            "format": (
                '{"level":"%(levelname)s","time":"%(asctime)s","logger":"%(name)s",'
                '"message":"%(message)s"}'
            ),
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "json",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "INFO",
    },
}
