"""Celery 采集任务入口。"""

from dataclasses import asdict
from typing import Any

from celery import Task, shared_task

from apps.collection.models import CollectionSchedule, CollectionStatus, CollectionTask, CollectionTaskType
from apps.collection.services.collection_runner import run_collection


@shared_task(name="system_ping")
def system_ping() -> dict[str, str]:
    return {"status": "ok"}


@shared_task(bind=True, name="run_collection_task", time_limit=12 * 60 * 60)
def run_collection_task(self: Task, task_id: int) -> dict[str, Any]:  # noqa: ARG001
    return asdict(run_collection(task_id))


@shared_task(name="run_scheduled_collection", time_limit=12 * 60 * 60)
def run_scheduled_collection(schedule_id: int) -> dict[str, Any]:
    schedule = CollectionSchedule.objects.select_related("source_target").get(pk=schedule_id)
    if not schedule.enabled or not schedule.source_target.is_active:
        return {"status": "skipped", "reason": "schedule_disabled"}

    active_statuses = (CollectionStatus.PENDING, CollectionStatus.RUNNING, CollectionStatus.PAUSED)
    if CollectionTask.objects.filter(source_target=schedule.source_target, status__in=active_statuses).exists():
        return {"status": "skipped", "reason": "collection_already_active"}

    task = CollectionTask.objects.create(
        source_target=schedule.source_target,
        task_type=CollectionTaskType.INCREMENTAL,
        requested_limit=None,
    )
    summary = run_collection(task.id)
    return {"status": "success", "task_id": task.id, **asdict(summary)}
