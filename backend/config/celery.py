"""Celery 应用初始化。"""

import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")

app = Celery("phone_voice_insight")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()

# Reconcile orphaned collection tasks independently of individual worker lifetimes.
app.conf.beat_schedule = {
    **(app.conf.beat_schedule or {}),
    "reconcile-collection-tasks": {
        "task": "reconcile_collection_tasks",
        "schedule": 60.0,
    },
}
