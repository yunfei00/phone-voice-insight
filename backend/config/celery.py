"""Celery 应用初始化。"""

import os

from celery import Celery
from celery.schedules import crontab

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
    "reconcile-automatic-voice-pipeline": {
        "task": "reconcile_automatic_voice_pipeline",
        "schedule": 300.0,
    },
    "recover-stale-governance-ai-batches": {
        "task": "recover_stale_governance_ai_batches",
        "schedule": 60.0,
    },
    "dispatch-pending-structured-reviews": {
        "task": "dispatch_pending_structured_reviews",
        "schedule": 1800.0,
    },
    "recover-stale-structured-batches": {
        "task": "recover_stale_structured_batches",
        "schedule": 300.0,
    },
    "dashboard-beat-heartbeat": {
        "task": "record_dashboard_beat_heartbeat",
        "schedule": 60.0,
    },
    "generate-daily-insight-reports": {
        "task": "generate_insight_reports",
        "schedule": crontab(hour=1, minute=10),
        "args": ("DAILY",),
    },
    "generate-weekly-insight-reports": {
        "task": "generate_insight_reports",
        "schedule": crontab(hour=1, minute=20, day_of_week="monday"),
        "args": ("WEEKLY",),
    },
}
