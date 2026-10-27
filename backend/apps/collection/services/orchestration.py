"""SourceTarget-level task admission and source-wide execution leases."""

from __future__ import annotations

from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from apps.collection.models import (
    CollectionSourceLease,
    CollectionStatus,
    CollectionTargetState,
    CollectionTargetStatus,
    CollectionTask,
    CollectionTaskType,
    CollectionTriggerType,
)
from apps.sources.models import SourceTarget

ACTIVE_STATUSES = (CollectionStatus.PENDING, CollectionStatus.RUNNING, CollectionStatus.PAUSED)
LEASE_TTL = timedelta(minutes=10)


class CollectionAlreadyActive(RuntimeError):
    def __init__(self, task_id: int) -> None:
        super().__init__(f"采集入口已有执行中的任务 #{task_id}")
        self.task_id = task_id


class CollectionSourceBusy(RuntimeError):
    def __init__(self, task_id: int) -> None:
        super().__init__(f"数据来源正在由任务 #{task_id} 采集")
        self.task_id = task_id


@transaction.atomic
def create_collection_task(
    *,
    source_target: SourceTarget,
    task_type: str,
    trigger_type: str = CollectionTriggerType.MANUAL,
    requested_limit: int | None = None,
) -> CollectionTask:
    state, _ = CollectionTargetState.objects.get_or_create(source_target=source_target)
    state = CollectionTargetState.objects.select_for_update().get(pk=state.pk)
    active = (
        CollectionTask.objects.filter(source_target=source_target, status__in=ACTIVE_STATUSES)
        .order_by("created_at", "id")
        .first()
    )
    if active is not None:
        if state.active_task_id != active.id:
            state.active_task = active
            state.save(update_fields=("active_task", "updated_at"))
        raise CollectionAlreadyActive(active.id)
    task = CollectionTask.objects.create(
        source_target=source_target,
        task_type=task_type,
        trigger_type=trigger_type,
        requested_limit=None if task_type == CollectionTaskType.FULL else requested_limit,
    )
    state.active_task = task
    state.status = (
        CollectionTargetStatus.FULL_RUNNING
        if task_type == CollectionTaskType.FULL
        else CollectionTargetStatus.INCREMENTAL_RUNNING
    )
    state.last_error = ""
    state.save(update_fields=("active_task", "status", "last_error", "updated_at"))
    return task


@transaction.atomic
def claim_existing_task(task: CollectionTask) -> CollectionTargetState:
    state, _ = CollectionTargetState.objects.get_or_create(source_target=task.source_target)
    state = CollectionTargetState.objects.select_for_update().get(pk=state.pk)
    active = (
        CollectionTask.objects.filter(source_target=task.source_target, status__in=ACTIVE_STATUSES)
        .exclude(pk=task.pk)
        .order_by("created_at", "id")
        .first()
    )
    if active is not None:
        raise CollectionAlreadyActive(active.id)
    state.active_task = task
    state.status = (
        CollectionTargetStatus.FULL_RUNNING
        if task.task_type == CollectionTaskType.FULL
        else CollectionTargetStatus.INCREMENTAL_RUNNING
    )
    state.save(update_fields=("active_task", "status", "updated_at"))
    return state


@transaction.atomic
def acquire_source_lease(task: CollectionTask) -> None:
    lease, _ = CollectionSourceLease.objects.get_or_create(source=task.source_target.source)
    lease = CollectionSourceLease.objects.select_for_update().get(pk=lease.pk)
    now = timezone.now()
    if lease.owner_task_id not in (None, task.id) and lease.expires_at and lease.expires_at > now:
        owner_task_id = lease.owner_task_id
        assert owner_task_id is not None
        raise CollectionSourceBusy(owner_task_id)
    lease.owner_task = task
    lease.expires_at = now + LEASE_TTL
    lease.save(update_fields=("owner_task", "expires_at", "updated_at"))


def refresh_source_lease(task_id: int) -> None:
    CollectionSourceLease.objects.filter(owner_task_id=task_id).update(
        expires_at=timezone.now() + LEASE_TTL,
        updated_at=timezone.now(),
    )


def release_source_lease(task_id: int) -> None:
    CollectionSourceLease.objects.filter(owner_task_id=task_id).update(
        owner_task=None,
        expires_at=None,
        updated_at=timezone.now(),
    )


@transaction.atomic
def release_target(task: CollectionTask, *, success: bool, verified: bool = False, error: str = "") -> None:
    state = CollectionTargetState.objects.select_for_update().get(source_target=task.source_target)
    if state.active_task_id == task.id:
        state.active_task = None
    now = timezone.now()
    if task.task_type == CollectionTaskType.FULL:
        state.last_full_task = task
        if verified:
            state.full_verified = True
            state.full_verified_at = now
            state.last_discovered_thread_count = int(task.verification_report.get("discovered_threads", 0))
            state.last_verified_thread_count = int(task.verification_report.get("thread_details_success", 0))
    else:
        state.last_incremental_task = task
    if success:
        state.last_success_at = now
        state.status = CollectionTargetStatus.READY if state.full_verified else CollectionTargetStatus.NOT_INITIALIZED
        state.last_error = ""
    else:
        state.last_failure_at = now
        state.status = CollectionTargetStatus.DEGRADED
        state.last_error = error
        if task.task_type == CollectionTaskType.FULL:
            state.full_verified = False
            state.full_verified_at = None
    state.save()
