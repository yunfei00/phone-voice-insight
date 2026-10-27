"""Celery 采集任务入口。"""

from dataclasses import asdict
from typing import Any

from celery import Task, shared_task
from collectors.base import CollectorError

from apps.collection.models import (
    CollectionSchedule,
    CollectionScheduleEvent,
    CollectionTargetState,
    CollectionTaskType,
    CollectionTriggerType,
)
from apps.collection.services.collection_runner import run_collection
from apps.collection.services.orchestration import (
    CollectionAlreadyActive,
    CollectionSourceBusy,
    create_collection_task,
)


@shared_task(name="system_ping")
def system_ping() -> dict[str, str]:
    return {"status": "ok"}


@shared_task(
    bind=True,
    name="run_collection_task",
    time_limit=30 * 60,
    soft_time_limit=29 * 60,
    acks_late=True,
    reject_on_worker_lost=True,
    max_retries=20,
)
def run_collection_task(self: Task, task_id: int) -> dict[str, Any]:
    try:
        summary = run_collection(task_id)
    except CollectionSourceBusy as exc:
        raise self.retry(exc=exc, countdown=60) from exc
    except CollectorError as exc:
        if exc.retryable and self.request.retries < 4:
            countdown = min(60 * (2**self.request.retries), 3600)
            raise self.retry(exc=exc, countdown=countdown) from exc
        raise
    if summary.continuation_required:
        self.apply_async(args=(task_id,), countdown=5)
    return asdict(summary)


@shared_task(name="run_scheduled_collection", time_limit=5 * 60)
def run_scheduled_collection(schedule_id: int) -> dict[str, Any]:
    schedule = CollectionSchedule.objects.select_related("source_target").get(pk=schedule_id)
    if not schedule.enabled or not schedule.source_target.is_active:
        return {"status": "skipped", "reason": "schedule_disabled"}

    state, _ = CollectionTargetState.objects.get_or_create(source_target=schedule.source_target)
    if not state.full_verified:
        CollectionScheduleEvent.objects.create(
            schedule=schedule,
            status="SKIPPED_NOT_INITIALIZED",
            reason="full_not_verified",
        )
        return {"status": "skipped", "reason": "full_not_verified"}
    try:
        task = create_collection_task(
            source_target=schedule.source_target,
            task_type=CollectionTaskType.INCREMENTAL,
            trigger_type=CollectionTriggerType.SCHEDULED,
        )
    except CollectionAlreadyActive as exc:
        CollectionScheduleEvent.objects.create(
            schedule=schedule,
            status="SKIPPED_BUSY",
            reason="collection_already_active",
            task_id=exc.task_id,
        )
        return {"status": "skipped", "reason": "collection_already_active", "task_id": exc.task_id}
    CollectionScheduleEvent.objects.create(schedule=schedule, status="QUEUED", task=task)
    async_result = run_collection_task.delay(task.id)
    return {"status": "queued", "task_id": task.id, "celery_task_id": async_result.id}
