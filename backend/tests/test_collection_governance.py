from datetime import timedelta
from uuid import uuid4

import pytest
from collectors.base import NormalizedReview
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.test import APIClient

from apps.collection.models import (
    CollectionSchedule,
    CollectionScheduleEvent,
    CollectionSourceLease,
    CollectionStatus,
    CollectionTargetState,
    CollectionTask,
    CollectionTaskType,
)
from apps.collection.services.orchestration import (
    CollectionAlreadyActive,
    CollectionSourceBusy,
    DuplicateCollectionExecution,
    acquire_source_lease,
    create_collection_task,
    release_source_lease,
)
from apps.collection.services.review_persistence import persist_review
from apps.collection.tasks import (
    dispatch_next_source_task,
    enqueue_collection_task,
    reconcile_collection_tasks,
    run_scheduled_collection,
)
from apps.products.models import Product
from apps.reviews.models import ReviewRecord
from apps.sources.models import DataSource, SourceTarget, SourceType


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("active_type", "requested_type"),
    [(CollectionTaskType.FULL, "INCREMENTAL"), (CollectionTaskType.INCREMENTAL, "FULL")],
)
def test_active_target_rejects_other_task_with_409(
    api_client: APIClient,
    source_target: SourceTarget,
    active_type: str,
    requested_type: str,
) -> None:
    active = create_collection_task(source_target=source_target, task_type=active_type)
    active.status = CollectionStatus.RUNNING
    active.save(update_fields=("status", "updated_at"))

    response = api_client.post(
        "/api/v1/collection-tasks/",
        {"source_target": source_target.id, "task_type": requested_type},
        format="json",
    )

    assert response.status_code == 409
    assert response.json()["code"] == "COLLECTION_ALREADY_ACTIVE"
    assert response.json()["active_task_id"] == active.id
    assert CollectionTask.objects.filter(source_target=source_target).count() == 1


@pytest.mark.django_db(transaction=True)
def test_admission_lock_allows_only_one_active_task(source_target: SourceTarget) -> None:
    first = create_collection_task(source_target=source_target, task_type=CollectionTaskType.FULL)
    with pytest.raises(CollectionAlreadyActive) as exc_info:
        create_collection_task(source_target=source_target, task_type=CollectionTaskType.INCREMENTAL)
    assert exc_info.value.task_id == first.id
    assert CollectionTask.objects.filter(source_target=source_target).count() == 1


@pytest.mark.django_db
def test_database_constraint_rejects_racing_active_insert(source_target: SourceTarget) -> None:
    CollectionTask.objects.create(source_target=source_target, task_type=CollectionTaskType.FULL)
    with pytest.raises(IntegrityError), transaction.atomic():
        CollectionTask.objects.create(source_target=source_target, task_type=CollectionTaskType.INCREMENTAL)


@pytest.mark.django_db
def test_honor_source_lease_serializes_different_targets(source_target: SourceTarget) -> None:
    honor_source, _ = DataSource.objects.update_or_create(
        code="HONOR_CLUB",
        defaults={"name": "荣耀俱乐部", "source_type": SourceType.COMMUNITY},
    )
    source_target.source = honor_source
    source_target.save(update_fields=("source", "updated_at"))
    second_product = Product.objects.create(
        brand=source_target.product.brand,
        name="荣耀 Power",
        normalized_name="HONOR_POWER",
    )
    second_target = SourceTarget.objects.create(
        source=source_target.source,
        product=second_product,
        name="第二个荣耀入口",
        target_type=source_target.target_type,
        target_url="https://club.honor.com/cn/threadtopic-596-1.html",
    )
    first = create_collection_task(source_target=source_target, task_type=CollectionTaskType.FULL)
    second = create_collection_task(source_target=second_target, task_type=CollectionTaskType.FULL)
    acquire_source_lease(first, uuid4())
    with pytest.raises(CollectionSourceBusy) as exc_info:
        acquire_source_lease(second, uuid4())
    assert exc_info.value.task_id == first.id


@pytest.mark.django_db
def test_same_source_tasks_are_dispatched_in_creation_order(
    source_target: SourceTarget,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    second_product = Product.objects.create(
        brand=source_target.product.brand,
        name="荣耀 Power",
        normalized_name="HONOR_POWER_QUEUE",
    )
    second_target = SourceTarget.objects.create(
        source=source_target.source,
        product=second_product,
        name="Power 入口",
        target_type=source_target.target_type,
    )
    first = create_collection_task(source_target=source_target, task_type=CollectionTaskType.FULL)
    second = create_collection_task(source_target=second_target, task_type=CollectionTaskType.FULL)
    submitted: list[int] = []

    class Result:
        id = "queued"

    def submit(args: tuple[object, ...], countdown: int = 0) -> Result:
        del countdown
        task_id = args[0]
        assert isinstance(task_id, int)
        submitted.append(task_id)
        return Result()

    monkeypatch.setattr(
        "apps.collection.tasks.run_collection_task.apply_async",
        submit,
    )
    assert enqueue_collection_task(first.id) is not None
    assert enqueue_collection_task(second.id) is None
    assert submitted == [first.id]

    first.status = CollectionStatus.FAILED
    first.save(update_fields=("status", "updated_at"))
    assert dispatch_next_source_task(source_target.source_id, force=True) is not None
    assert submitted == [first.id, second.id]


@pytest.mark.django_db
def test_live_source_lease_keeps_other_product_waiting(source_target: SourceTarget) -> None:
    second_product = Product.objects.create(
        brand=source_target.product.brand,
        name="荣耀 Power",
        normalized_name="HONOR_POWER_WAIT",
    )
    second_target = SourceTarget.objects.create(
        source=source_target.source,
        product=second_product,
        name="Power 入口",
        target_type=source_target.target_type,
    )
    first = create_collection_task(source_target=source_target, task_type=CollectionTaskType.FULL)
    first.status = CollectionStatus.RUNNING
    first.save(update_fields=("status", "updated_at"))
    acquire_source_lease(first, uuid4())
    second = create_collection_task(source_target=second_target, task_type=CollectionTaskType.FULL)

    assert enqueue_collection_task(second.id) is None
    second.refresh_from_db()
    assert second.status == CollectionStatus.PENDING
    assert f"#{first.id}" in second.waiting_reason


@pytest.mark.django_db
def test_duplicate_dispatch_token_cannot_start_two_runs(source_target: SourceTarget) -> None:
    from apps.collection.services.collection_runner import _start_run

    task = create_collection_task(source_target=source_target, task_type=CollectionTaskType.FULL)
    token = uuid4()
    task.dispatch_token = token
    task.save(update_fields=("dispatch_token", "updated_at"))
    _start_run(task.id, token)
    with pytest.raises(DuplicateCollectionExecution):
        _start_run(task.id, token)
    assert task.runs.count() == 1
    release_source_lease(task.id)


@pytest.mark.django_db
def test_watchdog_recovers_lost_worker_without_losing_checkpoint(
    source_target: SourceTarget,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from apps.collection.services.collection_runner import _start_run

    task = create_collection_task(source_target=source_target, task_type=CollectionTaskType.FULL)
    token = uuid4()
    task.dispatch_token = token
    task.last_checkpoint = {"phase": "collection", "current_thread_id": "123"}
    task.save(update_fields=("dispatch_token", "last_checkpoint", "updated_at"))
    _start_run(task.id, token)
    old = timezone.now() - timedelta(minutes=20)
    CollectionTask.objects.filter(pk=task.id).update(heartbeat_at=old, updated_at=old)
    CollectionSourceLease.objects.filter(source=task.source_target.source).update(expires_at=old)

    class Result:
        id = "recovered"

    def submit_recovery(args: tuple[object, ...], countdown: int = 0) -> Result:
        del args, countdown
        return Result()

    monkeypatch.setattr(
        "apps.collection.tasks.run_collection_task.apply_async",
        submit_recovery,
    )
    outcome = reconcile_collection_tasks.run()
    task.refresh_from_db()
    assert outcome["recovered"] == 1
    assert outcome["dispatched"] == 1
    assert task.status == CollectionStatus.PENDING
    assert task.last_checkpoint == {"phase": "collection", "current_thread_id": "123"}
    assert task.dispatch_token is not None


@pytest.mark.django_db
def test_schedule_busy_is_recorded_without_new_task(source_target: SourceTarget) -> None:
    schedule = CollectionSchedule.objects.create(source_target=source_target, enabled=True, interval_hours=6)
    state = CollectionTargetState.objects.get(source_target=source_target)
    state.full_verified = True
    state.save(update_fields=("full_verified", "updated_at"))
    active = create_collection_task(source_target=source_target, task_type=CollectionTaskType.FULL)

    result = run_scheduled_collection.run(schedule.id)

    assert result == {"status": "skipped", "reason": "collection_already_active", "task_id": active.id}
    assert CollectionScheduleEvent.objects.get().status == "SKIPPED_BUSY"
    assert CollectionTask.objects.count() == 1


@pytest.mark.django_db
def test_schedule_requires_verified_full(source_target: SourceTarget) -> None:
    schedule = CollectionSchedule.objects.create(source_target=source_target, enabled=True, interval_hours=6)
    result = run_scheduled_collection.run(schedule.id)
    assert result == {"status": "skipped", "reason": "full_not_verified"}
    assert CollectionScheduleEvent.objects.get().status == "SKIPPED_NOT_INITIALIZED"
    assert CollectionTask.objects.count() == 0


@pytest.mark.django_db
def test_ready_schedule_queues_one_incremental(
    source_target: SourceTarget,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    schedule = CollectionSchedule.objects.create(source_target=source_target, enabled=True, interval_hours=6)
    state = CollectionTargetState.objects.get(source_target=source_target)
    state.full_verified = True
    state.full_verified_at = timezone.now()
    state.save(update_fields=("full_verified", "full_verified_at", "updated_at"))

    class Result:
        id = "scheduled-celery-id"

    monkeypatch.setattr("apps.collection.tasks.enqueue_collection_task", lambda _task_id, **_kwargs: Result())
    result = run_scheduled_collection.run(schedule.id)

    task = CollectionTask.objects.get()
    assert result["status"] == "queued"
    assert task.task_type == CollectionTaskType.INCREMENTAL
    assert task.trigger_type == "SCHEDULED"
    assert CollectionScheduleEvent.objects.get().status == "QUEUED"


@pytest.mark.django_db
def test_schedule_api_updates_one_row(api_client: APIClient, source_target: SourceTarget) -> None:
    for hours in (6, 12):
        response = api_client.post(
            "/api/v1/collection-schedules/",
            {"source_target": source_target.id, "enabled": True, "interval_hours": hours},
            format="json",
        )
        assert response.status_code == 201
    assert CollectionSchedule.objects.count() == 1
    assert CollectionSchedule.objects.get().interval_hours == 12


@pytest.mark.django_db
def test_history_is_preserved_when_control_state_exists(source_target: SourceTarget) -> None:
    old = CollectionTask.objects.create(
        source_target=source_target,
        task_type=CollectionTaskType.FULL,
        status=CollectionStatus.SUCCESS,
        finished_at=timezone.now() - timedelta(days=1),
    )
    CollectionTargetState.objects.get(source_target=source_target)
    assert CollectionTask.objects.filter(pk=old.pk).exists()


@pytest.mark.django_db
def test_existing_thread_refreshes_dynamic_metadata_without_rewriting_content(source_target: SourceTarget) -> None:
    original = NormalizedReview(
        external_id="thread:dynamic",
        parent_external_id=None,
        record_type="THREAD",
        title="原始标题",
        content="原始正文",
        raw_data={"view_count": "100", "reply_count": "10", "like_count": "3"},
    )
    created = persist_review(source_target, original)
    refreshed = persist_review(
        source_target,
        NormalizedReview(
            external_id="thread:dynamic",
            parent_external_id=None,
            record_type="THREAD",
            title="修正标题",
            content="来源临时变化的正文",
            raw_data={"view_count": "150", "reply_count": "12", "like_count": "4"},
        ),
    )
    record = ReviewRecord.objects.get(pk=created.review.id)
    assert not refreshed.inserted and refreshed.updated
    assert record.title == "修正标题"
    assert record.content == "原始正文"
    assert record.raw_data == {"view_count": "150", "reply_count": "12", "like_count": "4"}
    assert ReviewRecord.objects.count() == 1
