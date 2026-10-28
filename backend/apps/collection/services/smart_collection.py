"""幂等的智能采集决策和 Celery 提交。"""

from __future__ import annotations

from dataclasses import dataclass

from django.db import transaction
from django.utils import timezone

from apps.collection.models import (
    CollectionStatus,
    CollectionTargetState,
    CollectionTask,
    CollectionTaskType,
    CollectionTriggerType,
    DiscoveryStatus,
)
from apps.collection.services.orchestration import (
    ACTIVE_STATUSES,
    CollectionAlreadyActive,
    claim_existing_task,
    create_collection_task,
    release_target,
)
from apps.sources.models import SourceTarget, TargetValidationStatus
from apps.sources.services.target_validation import target_url_hash


class SmartCollectionRejected(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class SmartCollectionResult:
    task: CollectionTask
    existing: bool
    recovered: bool
    celery_task_id: str = ""


def _recoverable_full(target: SourceTarget) -> CollectionTask | None:
    task = (
        target.collection_tasks.filter(task_type=CollectionTaskType.FULL, status=CollectionStatus.FAILED)
        .order_by("-created_at")
        .first()
    )
    if task is None or not task.last_checkpoint or not task.discovered_threads.exists():
        return None
    phase = str(task.last_checkpoint.get("phase", ""))
    if phase not in {"discovery", "collection", "verification", "completed"}:
        return None
    return task


@transaction.atomic
def _admit(source_target_id: int) -> tuple[CollectionTask, bool, bool]:
    target = SourceTarget.objects.select_for_update().select_related("source", "product").get(pk=source_target_id)
    if not target.is_active or not target.source.is_active or not target.target_url:
        raise SmartCollectionRejected("TARGET_NOT_CONFIGURED", "采集入口未配置或未启用")
    if target.validation_status != TargetValidationStatus.VALID or target.validated_url_hash != target_url_hash(
        target.target_url
    ):
        raise SmartCollectionRejected("TARGET_NOT_VALIDATED", "采集入口尚未验证或网址已变更")
    state, _ = CollectionTargetState.objects.get_or_create(source_target=target)
    state = CollectionTargetState.objects.select_for_update().get(pk=state.pk)
    active = target.collection_tasks.filter(status__in=ACTIVE_STATUSES).order_by("created_at", "id").first()
    if active is not None:
        return active, True, False

    if not state.full_verified:
        recovery = _recoverable_full(target)
        if recovery is not None:
            if recovery.last_checkpoint.get("phase") == "completed":
                recovery.discovered_threads.filter(status=DiscoveryStatus.FAILED).update(
                    status=DiscoveryStatus.PENDING,
                    attempts=0,
                    last_error="",
                )
                recovery.last_checkpoint = {**recovery.last_checkpoint, "phase": "collection", "completed": False}
            recovery.trigger_type = CollectionTriggerType.RECOVERY
            recovery.status = CollectionStatus.PENDING
            recovery.finished_at = None
            recovery.error_message = ""
            recovery.save(
                update_fields=(
                    "trigger_type",
                    "status",
                    "finished_at",
                    "error_message",
                    "last_checkpoint",
                    "updated_at",
                )
            )
            claim_existing_task(recovery)
            return recovery, False, True
        task_type = CollectionTaskType.FULL
    else:
        task_type = CollectionTaskType.INCREMENTAL
    try:
        task = create_collection_task(
            source_target=target,
            task_type=task_type,
            trigger_type=CollectionTriggerType.MANUAL,
        )
    except CollectionAlreadyActive as exc:
        return CollectionTask.objects.get(pk=exc.task_id), True, False
    return task, False, False


def _mark_submission_failed(task: CollectionTask, error: Exception) -> None:
    safe_error = f"CELERY_SUBMISSION_FAILED: {type(error).__name__}"
    with transaction.atomic():
        locked = CollectionTask.objects.select_for_update().select_related("source_target").get(pk=task.pk)
        if locked.status == CollectionStatus.PENDING:
            locked.status = CollectionStatus.FAILED
            locked.finished_at = timezone.now()
            locked.error_message = safe_error
            locked.save(update_fields=("status", "finished_at", "error_message", "updated_at"))
            release_target(locked, success=False, error=safe_error)


def start_smart_collection(source_target_id: int) -> SmartCollectionResult:
    task, existing, recovered = _admit(source_target_id)
    if existing:
        return SmartCollectionResult(task=task, existing=True, recovered=False)
    from apps.collection.tasks import enqueue_collection_task

    try:
        async_result = enqueue_collection_task(task.id)
    except Exception as exc:
        _mark_submission_failed(task, exc)
        raise SmartCollectionRejected("CELERY_SUBMISSION_FAILED", "采集任务提交失败; 请检查 Celery 和 Redis") from exc
    return SmartCollectionResult(
        task=task,
        existing=False,
        recovered=recovered,
        celery_task_id=str(getattr(async_result, "id", "")),
    )
