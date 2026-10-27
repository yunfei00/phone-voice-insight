"""Celery Beat 定时采集配置同步。"""

import json

from django_celery_beat.models import IntervalSchedule, PeriodicTask

from apps.collection.models import CollectionSchedule


def _periodic_task_name(schedule_id: int) -> str:
    return f"collection-schedule:{schedule_id}"


def sync_collection_schedule(schedule: CollectionSchedule) -> None:
    interval, _ = IntervalSchedule.objects.get_or_create(
        every=schedule.interval_hours,
        period=IntervalSchedule.HOURS,
    )
    PeriodicTask.objects.update_or_create(
        name=_periodic_task_name(schedule.id),
        defaults={
            "task": "run_scheduled_collection",
            "interval": interval,
            "crontab": None,
            "solar": None,
            "clocked": None,
            "args": json.dumps([schedule.id]),
            "enabled": schedule.enabled,
        },
    )


def delete_collection_schedule(schedule: CollectionSchedule) -> None:
    PeriodicTask.objects.filter(name=_periodic_task_name(schedule.id)).delete()
