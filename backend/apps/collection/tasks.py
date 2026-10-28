"""Celery 采集任务入口。"""

from dataclasses import asdict
from datetime import timedelta

from django.core.cache import cache
from django.db import transaction
from django.utils import timezone
from typing import Any

from celery import Task, shared_task
from collectors.base import CollectorError

from apps.collection.models import (
    CollectionSchedule,
    CollectionSourceLease,
    CollectionStatus,
    CollectionTask,
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
    recover_stale_stopping_tasks,
    release_source_lease,
    release_target,
)
from apps.sources.models import TargetValidationStatus


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
    if (
        schedule.source_target.source.code == "HONOR_CLUB"
        and schedule.source_target.validation_status != TargetValidationStatus.VALID
    ):
        CollectionScheduleEvent.objects.create(
            schedule=schedule,
            status="SKIPPED_TARGET_INVALID",
            reason="target_not_validated",
        )
        return {"status": "skipped", "reason": "target_not_validated"}

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


@shared_task(name="reconcile_collection_tasks", time_limit=120)
def reconcile_collection_tasks() -> dict[str, int]:
    """Periodic safety net for worker loss, abandoned stops and queued work."""
    now = timezone.now()
    recovered = dispatched = 0
    product_ids = list(
        CollectionTask.objects.filter(status=CollectionStatus.STOPPING)
        .values_list("source_target__product_id", flat=True).distinct()
    )
    from apps.products.models import Product

    for product_id in product_ids:
        with transaction.atomic():
            Product.objects.select_for_update().get(pk=product_id)
            recovered += recover_stale_stopping_tasks(product_id)

    stale = CollectionTask.objects.filter(
        status=CollectionStatus.RUNNING,
        updated_at__lt=now - timedelta(minutes=15),
    ).select_related("source_target")
    for candidate in stale:
        with transaction.atomic():
            task = CollectionTask.objects.select_for_update().get(pk=candidate.pk)
            if task.status != CollectionStatus.RUNNING or task.updated_at > timezone.now() - timedelta(minutes=15):
                continue
            lease = CollectionSourceLease.objects.select_for_update().filter(
                source_id=task.source_target.source_id
            ).first()
            if lease and lease.owner_task_id == task.id and lease.expires_at and lease.expires_at > timezone.now():
                continue
            task.status = CollectionStatus.FAILED
            task.finished_at = timezone.now()
            task.error_message = "WORKER_LOST: 超过 15 分钟未更新且租约失效"
            task.save(update_fields=("status", "finished_at", "error_message", "updated_at"))
            task.runs.filter(status=CollectionStatus.RUNNING).update(
                status=CollectionStatus.FAILED, finished_at=timezone.now(), error_message=task.error_message
            )
            release_source_lease(task.id)
            release_target(task, success=False, error=task.error_message)
            recovered += 1

    # Redis cache add is atomic; prevent repeated beat ticks from flooding the broker.
    for task in CollectionTask.objects.filter(status=CollectionStatus.PENDING).order_by("created_at", "id"):
        lease = CollectionSourceLease.objects.filter(source_id=task.source_target.source_id).first()
        if lease and lease.owner_task_id not in (None, task.id) and lease.expires_at and lease.expires_at > timezone.now():
            continue
        if cache.add(f"collection:dispatch:{task.id}", True, timeout=90):
            run_collection_task.delay(task.id)
            dispatched += 1
    return {"recovered": recovered, "dispatched": dispatched}
