"""Celery 采集任务入口。"""

import logging
from dataclasses import asdict
from datetime import timedelta
from typing import Any
from uuid import UUID, uuid4

from celery import Task, shared_task
from collectors.base import CollectorError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.collection.models import (
    CollectionSchedule,
    CollectionScheduleEvent,
    CollectionSourceLease,
    CollectionStatus,
    CollectionTargetState,
    CollectionTask,
    CollectionTaskType,
    CollectionTriggerType,
)
from apps.collection.services.collection_runner import run_collection
from apps.collection.services.orchestration import (
    CollectionAlreadyActive,
    CollectionSourceBusy,
    DuplicateCollectionExecution,
    StaleCollectionExecution,
    create_collection_task,
    mark_task_waiting,
    recover_stale_stopping_tasks,
    release_source_lease,
)
from apps.sources.models import DataSource, TargetValidationStatus

DISPATCH_RETRY_AFTER = timedelta(minutes=2)
logger = logging.getLogger(__name__)


def enqueue_collection_task(
    task_id: int,
    *,
    countdown: int = 0,
    force: bool = False,
) -> Any | None:
    """Persist a generation token before broker submission.

    Only the oldest pending task for a source may be submitted. A lost broker
    message becomes eligible again after DISPATCH_RETRY_AFTER.
    """
    with transaction.atomic():
        candidate = CollectionTask.objects.select_related("source_target").get(pk=task_id)
        DataSource.objects.select_for_update().get(pk=candidate.source_target.source_id)
        task = CollectionTask.objects.select_for_update().select_related("source_target").get(pk=task_id)
        if task.status != CollectionStatus.PENDING:
            return None
        oldest = (
            CollectionTask.objects.filter(
                source_target__source_id=task.source_target.source_id,
                status=CollectionStatus.PENDING,
            )
            .order_by("created_at", "id")
            .first()
        )
        if oldest is None or oldest.id != task.id:
            return None
        now = timezone.now()
        lease = CollectionSourceLease.objects.select_for_update().filter(source_id=task.source_target.source_id).first()
        if lease and lease.owner_task_id not in (None, task.id) and lease.expires_at and lease.expires_at > now:
            task.waiting_reason = f"等待同来源任务 #{lease.owner_task_id} 完成"
            task.save(update_fields=("waiting_reason", "updated_at"))
            return None
        if not force and task.dispatched_at and task.dispatched_at > now - DISPATCH_RETRY_AFTER:
            return None
        token = uuid4()
        task.dispatch_token = token
        task.dispatched_at = now
        task.waiting_reason = "已进入执行队列"
        task.save(update_fields=("dispatch_token", "dispatched_at", "waiting_reason", "updated_at"))
    try:
        return run_collection_task.apply_async(args=(task.id, str(token)), countdown=countdown)
    except Exception:
        mark_task_waiting(task.id, reason="消息队列提交失败。等待巡检重试", dispatch_token=token)
        raise


def dispatch_next_source_task(source_id: int, *, force: bool = False) -> Any | None:
    next_task = (
        CollectionTask.objects.filter(source_target__source_id=source_id, status=CollectionStatus.PENDING)
        .order_by("created_at", "id")
        .first()
    )
    if next_task is None:
        return None
    return enqueue_collection_task(next_task.id, force=force)


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
    max_retries=0,
)
def run_collection_task(_self: Task, task_id: int, dispatch_token: str | None = None) -> dict[str, Any]:
    task = CollectionTask.objects.select_related("source_target").filter(pk=task_id).first()
    if task is None:
        return {"status": "ignored", "reason": "task_not_found"}
    source_id = task.source_target.source_id
    if dispatch_token is None:
        queued = enqueue_collection_task(task_id, force=True)
        return {"status": "requeued", "celery_task_id": str(getattr(queued, "id", ""))}
    try:
        summary = run_collection(task_id, dispatch_token=dispatch_token)
    except CollectionSourceBusy as exc:
        mark_task_waiting(
            task_id,
            reason=f"等待同来源任务 #{exc.task_id} 完成",
            dispatch_token=UUID(dispatch_token),
        )
        return {"status": "waiting", "reason": "source_busy", "owner_task_id": exc.task_id}
    except (DuplicateCollectionExecution, StaleCollectionExecution) as exc:
        return {"status": "ignored", "reason": type(exc).__name__}
    except CollectorError:
        dispatch_next_source_task(source_id, force=True)
        raise
    except Exception:
        dispatch_next_source_task(source_id, force=True)
        raise
    if summary.continuation_required:
        enqueue_collection_task(task_id, countdown=5, force=True)
    else:
        if summary.completed and max(summary.new_records, summary.inserted_records) > 0:
            try:
                from apps.reviews.tasks import run_automatic_voice_pipeline

                run_automatic_voice_pipeline.delay(task.source_target.product_id, source_id)
            except Exception:
                logger.exception("automatic_pipeline_dispatch_failed collection_task_id=%s", task_id)
        dispatch_next_source_task(source_id, force=True)
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
    async_result = enqueue_collection_task(task.id)
    return {
        "status": "queued" if async_result is not None else "waiting",
        "task_id": task.id,
        "celery_task_id": str(getattr(async_result, "id", "")),
    }


@shared_task(name="reconcile_collection_tasks", time_limit=120)
def reconcile_collection_tasks() -> dict[str, int]:
    """Periodic safety net for worker loss, abandoned stops and queued work."""
    now = timezone.now()
    recovered = dispatched = 0
    product_ids = list(
        CollectionTask.objects.filter(status=CollectionStatus.STOPPING)
        .values_list("source_target__product_id", flat=True)
        .distinct()
    )
    from apps.products.models import Product

    for product_id in product_ids:
        with transaction.atomic():
            Product.objects.select_for_update().get(pk=product_id)
            recovered += recover_stale_stopping_tasks(product_id)

    stale = (
        CollectionTask.objects.filter(status=CollectionStatus.RUNNING)
        .filter(
            Q(heartbeat_at__isnull=True, updated_at__lt=now - timedelta(minutes=15))
            | Q(heartbeat_at__lt=now - timedelta(minutes=15))
        )
        .select_related("source_target")
    )
    for candidate in stale:
        with transaction.atomic():
            task = CollectionTask.objects.select_for_update().get(pk=candidate.pk)
            heartbeat = task.heartbeat_at or task.updated_at
            if task.status != CollectionStatus.RUNNING or heartbeat > timezone.now() - timedelta(minutes=15):
                continue
            lease = (
                CollectionSourceLease.objects.select_for_update().filter(source_id=task.source_target.source_id).first()
            )
            if lease and lease.owner_task_id == task.id and lease.expires_at and lease.expires_at > timezone.now():
                continue
            old_token = task.execution_token
            task.status = CollectionStatus.PENDING
            task.finished_at = None
            task.execution_token = None
            task.heartbeat_at = None
            task.dispatch_token = None
            task.dispatched_at = None
            task.waiting_reason = "Worker 失联。等待从检查点恢复"
            task.error_message = "WORKER_LOST_RECOVERY: 心跳超时且来源租约失效"
            task.save(
                update_fields=(
                    "status",
                    "finished_at",
                    "execution_token",
                    "heartbeat_at",
                    "dispatch_token",
                    "dispatched_at",
                    "waiting_reason",
                    "error_message",
                    "updated_at",
                )
            )
            task.runs.filter(status=CollectionStatus.RUNNING).update(
                status=CollectionStatus.FAILED, finished_at=timezone.now(), error_message=task.error_message
            )
            release_source_lease(task.id, old_token)
            CollectionTargetState.objects.filter(source_target=task.source_target).update(
                active_task=task,
                status="WAITING",
                last_error=task.error_message,
                updated_at=timezone.now(),
            )
            recovered += 1

    source_ids = (
        CollectionTask.objects.filter(status=CollectionStatus.PENDING)
        .values_list("source_target__source_id", flat=True)
        .distinct()
    )
    dispatch_failed = 0
    for source_id in source_ids:
        try:
            if dispatch_next_source_task(source_id) is not None:
                dispatched += 1
        except Exception:
            # enqueue_collection_task persists the pending state for the next
            # reconciliation tick. One broken broker submission must not block
            # other independent sources.
            dispatch_failed += 1
            logger.exception("collection_reconcile_dispatch_failed source_id=%s", source_id)
    return {"recovered": recovered, "dispatched": dispatched, "dispatch_failed": dispatch_failed}
