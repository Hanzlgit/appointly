"""Celery application for appointly."""

import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
os.environ.setdefault("OTEL_SERVICE_NAME", "appointly-worker")

app = Celery("appointly")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
