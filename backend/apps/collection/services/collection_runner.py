"""采集任务编排、checkpoint 与统计。"""

from __future__ import annotations

import logging
from collections import Counter
from dataclasses import dataclass
from typing import Any
from uuid import UUID, uuid4

from collectors.base import (
    BaseCollector,
    CollectionCheckpoint,
    CollectionRequest,
    CollectorError,
    CollectorTarget,
    NormalizedReview,
)
from collectors.honor_club.normalizer import is_product_related
from collectors.honor_club.parser import extract_thread_page_count, is_valid_thread_page
from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from apps.collection.models import (
    CollectionRun,
    CollectionStatus,
    CollectionTargetState,
    CollectionTargetStatus,
    CollectionTask,
    CollectionTaskType,
)
from apps.collection.services.collector_registry import get_collector
from apps.collection.services.honor_full import run_honor_full_chunk
from apps.collection.services.orchestration import (
    DuplicateCollectionExecution,
    StaleCollectionExecution,
    acquire_source_lease,
    claim_existing_task,
    refresh_source_lease,
    release_source_lease,
    release_target,
)
from apps.collection.services.review_persistence import persist_review
from apps.products.models import ProductAlias
from apps.reviews.models import ReviewRecord
from apps.sources.models import SourceTarget

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CollectionSummary:
    scanned_threads: int
    inserted_records: int
    skipped_records: int
    failed_records: int
    record_types: dict[str, int]
    samples: list[dict[str, Any]]
    new_threads: int = 0
    known_threads: int = 0
    new_records: int = 0
    duplicate_records: int = 0
    stopped_at_known_boundary: bool = False
    completed: bool = True
    continuation_required: bool = False
    completion_verified: bool = False
    verification_report: dict[str, Any] | None = None


def _int_config(config: dict[str, Any], name: str, default: int, maximum: int) -> int:
    try:
        value = int(config.get(name, default))
    except (TypeError, ValueError):
        value = default
    return min(max(value, 1), maximum)


def _build_collector_target(source_target: SourceTarget, *, target_url: str | None = None) -> CollectorTarget:
    aliases = list(ProductAlias.objects.filter(product=source_target.product).values_list("alias", flat=True))
    if source_target.product.name not in aliases:
        aliases.append(source_target.product.name)
    config = dict(source_target.config_json)
    config["product_aliases"] = aliases
    sibling_products = source_target.product.brand.products.exclude(pk=source_target.product_id).prefetch_related(
        "aliases"
    )
    excluded_aliases: list[str] = []
    for product in sibling_products:
        excluded_aliases.append(product.name)
        excluded_aliases.extend(alias.alias for alias in product.aliases.all())
    config["excluded_product_aliases"] = excluded_aliases
    return CollectorTarget(
        source_code=source_target.source.code,
        product_code=source_target.product.normalized_name,
        target_url=target_url or source_target.target_url,
        external_id=source_target.external_id,
        config=config,
    )


def _start_run(task_id: int, dispatch_token: UUID) -> tuple[CollectionTask, CollectionRun]:
    with transaction.atomic():
        candidate = CollectionTask.objects.select_related("source_target").get(pk=task_id)
        # Match admission lock order before taking the task row lock.
        from apps.products.models import Product
        from apps.sources.models import DataSource

        DataSource.objects.select_for_update().get(pk=candidate.source_target.source_id)
        Product.objects.select_for_update().get(pk=candidate.source_target.product_id)
        task = (
            CollectionTask.objects.select_for_update()
            .select_related("source_target__source", "source_target__product")
            .get(pk=task_id)
        )
        if task.status in (CollectionStatus.STOPPING, CollectionStatus.CANCELLED):
            raise CollectionStopRequested()
        if task.status != CollectionStatus.PENDING or task.dispatch_token != dispatch_token:
            raise DuplicateCollectionExecution(f"任务 #{task.id} 的派发消息已失效")
        claim_existing_task(task)
        execution_token = uuid4()
        task.execution_token = execution_token
        acquire_source_lease(task, execution_token)
        task.runs.filter(status=CollectionStatus.RUNNING).update(
            status=CollectionStatus.FAILED,
            finished_at=timezone.now(),
            error_message="WORKER_RECOVERY: 上次运行中断; 已从持久化检查点恢复",
        )
        task.transition_to(CollectionStatus.RUNNING)
        started_at = timezone.now()
        task.started_at = started_at
        task.finished_at = None
        if not task.last_checkpoint:
            task.success_count = 0
            task.skipped_count = 0
            task.failure_count = 0
            task.new_threads = 0
            task.known_threads = 0
            task.new_records = 0
            task.duplicate_records = 0
            task.stopped_at_known_boundary = False
        task.error_message = ""
        task.waiting_reason = ""
        task.dispatch_token = None
        task.dispatched_at = None
        task.heartbeat_at = started_at
        task.save(
            update_fields=(
                "status",
                "started_at",
                "finished_at",
                "success_count",
                "skipped_count",
                "failure_count",
                "new_threads",
                "known_threads",
                "new_records",
                "duplicate_records",
                "stopped_at_known_boundary",
                "error_message",
                "waiting_reason",
                "dispatch_token",
                "dispatched_at",
                "execution_token",
                "heartbeat_at",
                "updated_at",
            )
        )
        CollectionTargetState.objects.filter(source_target=task.source_target, active_task=task).update(
            status=(
                CollectionTargetStatus.FULL_RUNNING
                if task.task_type == CollectionTaskType.FULL
                else CollectionTargetStatus.INCREMENTAL_RUNNING
            ),
            updated_at=started_at,
        )
        latest_run = task.runs.aggregate(max_number=Max("run_number"))["max_number"] or 0
        run = CollectionRun.objects.create(
            task=task,
            run_number=latest_run + 1,
            status=CollectionStatus.RUNNING,
            started_at=started_at,
            execution_token=execution_token,
        )
    return task, run


def _save_progress(
    task_id: int,
    run_id: int,
    *,
    inserted: int,
    skipped: int,
    failed: int,
    checkpoint: dict[str, Any],
    progress_stats: dict[str, int | bool] | None = None,
) -> None:
    with transaction.atomic():
        task = CollectionTask.objects.select_for_update().get(pk=task_id)
        run = CollectionRun.objects.select_for_update().get(pk=run_id)
        if run.execution_token is None or task.execution_token != run.execution_token:
            raise StaleCollectionExecution(f"任务 #{task_id} 的旧执行实例已失效")
        execution_token = run.execution_token
        task.success_count = inserted
        task.skipped_count = skipped
        task.failure_count = failed
        task.last_checkpoint = checkpoint
        task.heartbeat_at = timezone.now()
        if progress_stats:
            task.new_threads = int(progress_stats.get("new_threads", 0))
            task.known_threads = int(progress_stats.get("known_threads", 0))
            task.new_records = int(progress_stats.get("new_records", inserted))
            task.duplicate_records = int(progress_stats.get("duplicate_records", skipped))
            task.stopped_at_known_boundary = bool(progress_stats.get("stopped_at_known_boundary", False))
        task.save(
            update_fields=(
                "success_count",
                "skipped_count",
                "failure_count",
                "last_checkpoint",
                "heartbeat_at",
                "new_threads",
                "known_threads",
                "new_records",
                "duplicate_records",
                "stopped_at_known_boundary",
                "updated_at",
            )
        )
        run.success_count = inserted
        run.skipped_count = skipped
        run.failure_count = failed
        run.checkpoint_json = checkpoint
        if progress_stats:
            run.new_threads = task.new_threads
            run.known_threads = task.known_threads
            run.new_records = task.new_records
            run.duplicate_records = task.duplicate_records
            run.stopped_at_known_boundary = task.stopped_at_known_boundary
        run.save(
            update_fields=(
                "success_count",
                "skipped_count",
                "failure_count",
                "checkpoint_json",
                "new_threads",
                "known_threads",
                "new_records",
                "duplicate_records",
                "stopped_at_known_boundary",
            )
        )
    refresh_source_lease(task_id, execution_token)


def _finish_success(
    task_id: int,
    run_id: int,
    *,
    verified: bool = False,
    report: dict[str, Any] | None = None,
) -> None:
    finished_at = timezone.now()
    with transaction.atomic():
        task = CollectionTask.objects.select_for_update().get(pk=task_id)
        run = CollectionRun.objects.select_for_update().get(pk=run_id)
        if run.execution_token is None or task.execution_token != run.execution_token:
            raise StaleCollectionExecution(f"任务 #{task_id} 的旧执行实例已失效")
        if task.status == CollectionStatus.STOPPING:
            raise CollectionStopRequested()
        task.transition_to(CollectionStatus.SUCCESS)
        task.finished_at = finished_at
        task.completion_verified = verified
        task.verification_report = report or {}
        execution_token = task.execution_token
        task.execution_token = None
        task.heartbeat_at = None
        task.save(
            update_fields=(
                "status",
                "finished_at",
                "completion_verified",
                "verification_report",
                "execution_token",
                "heartbeat_at",
                "updated_at",
            )
        )
        run.status = CollectionStatus.SUCCESS
        run.finished_at = finished_at
        run.completion_verified = verified
        run.verification_report = report or {}
        run.save(update_fields=("status", "finished_at", "completion_verified", "verification_report"))
    release_source_lease(task_id, execution_token)
    release_target(task, success=True, verified=verified)


def _finish_failed(task_id: int, run_id: int, message: str) -> None:
    finished_at = timezone.now()
    with transaction.atomic():
        task = CollectionTask.objects.select_for_update().get(pk=task_id)
        run = CollectionRun.objects.select_for_update().get(pk=run_id)
        if run.execution_token is None or task.execution_token != run.execution_token:
            raise StaleCollectionExecution(f"任务 #{task_id} 的旧执行实例已失效")
        task.transition_to(CollectionStatus.FAILED)
        task.finished_at = finished_at
        task.failure_count += 1
        task.error_message = message
        execution_token = task.execution_token
        task.execution_token = None
        task.heartbeat_at = None
        task.save(
            update_fields=(
                "status",
                "finished_at",
                "failure_count",
                "error_message",
                "execution_token",
                "heartbeat_at",
                "updated_at",
            )
        )
        run.status = CollectionStatus.FAILED
        run.finished_at = finished_at
        run.failure_count = task.failure_count
        run.error_message = message
        run.save(update_fields=("status", "finished_at", "failure_count", "error_message"))
    release_source_lease(task_id, execution_token)
    release_target(task, success=False, error=message)


def _finish_continuation(task_id: int, run_id: int) -> None:
    finished_at = timezone.now()
    with transaction.atomic():
        task = CollectionTask.objects.select_for_update().get(pk=task_id)
        run = CollectionRun.objects.select_for_update().get(pk=run_id)
        if run.execution_token is None or task.execution_token != run.execution_token:
            raise StaleCollectionExecution(f"任务 #{task_id} 的旧执行实例已失效")
        if task.status == CollectionStatus.STOPPING:
            raise CollectionStopRequested()
        task.transition_to(CollectionStatus.SUCCESS)
        task.transition_to(CollectionStatus.PENDING)
        execution_token = task.execution_token
        task.execution_token = None
        task.heartbeat_at = None
        task.waiting_reason = "等待下一采集分块"
        task.save(update_fields=("status", "execution_token", "heartbeat_at", "waiting_reason", "updated_at"))
        run.status = CollectionStatus.SUCCESS
        run.finished_at = finished_at
        run.save(update_fields=("status", "finished_at"))
    refresh_source_lease(task_id, execution_token)


class CollectionStopRequested(Exception):
    """Cooperative cancellation; never treat a user stop as a collection failure."""


def check_collection_stop(task_id: int) -> None:
    if CollectionTask.objects.filter(
        pk=task_id, status__in=(CollectionStatus.STOPPING, CollectionStatus.CANCELLED)
    ).exists():
        raise CollectionStopRequested()


def _finish_stopped(task_id: int, run_id: int) -> None:
    now = timezone.now()
    with transaction.atomic():
        task = CollectionTask.objects.select_for_update().get(pk=task_id)
        run = CollectionRun.objects.select_for_update().get(pk=run_id)
        if run.execution_token is None or task.execution_token != run.execution_token:
            raise StaleCollectionExecution(f"任务 #{task_id} 的旧执行实例已失效")
        if task.status == CollectionStatus.STOPPING:
            task.transition_to(CollectionStatus.CANCELLED)
        task.finished_at = now
        execution_token = task.execution_token
        task.execution_token = None
        task.heartbeat_at = None
        task.save(update_fields=("status", "finished_at", "execution_token", "heartbeat_at", "updated_at"))
        CollectionRun.objects.filter(pk=run_id, status=CollectionStatus.RUNNING).update(
            status=CollectionStatus.CANCELLED, finished_at=now
        )
    release_source_lease(task_id, execution_token)
    release_target(task, success=False, error="用户主动停止采集")


def _request_log(task_id: int, source: str, page: int, thread_id: str, metadata: dict[str, Any]) -> None:
    logger.info(
        "collection_request collection_task_id=%s source=%s topic_page=%s thread_id=%s "
        "request_url=%s http_status=%s elapsed_ms=%s",
        task_id,
        source,
        page,
        thread_id,
        metadata.get("request_url", ""),
        metadata.get("http_status", ""),
        metadata.get("elapsed_ms", ""),
    )


def _sample_review(normalized: NormalizedReview, review_id: int | None = None) -> dict[str, Any]:
    sample = {
        "external_id": normalized.external_id,
        "record_type": normalized.record_type,
        "content_preview": normalized.content[:100],
        "rating": normalized.rating,
        "published_at": normalized.published_at.isoformat() if normalized.published_at else None,
        "variant_external_id": normalized.variant_external_id,
        "variant_attributes": normalized.variant_attributes,
        "is_append_review": normalized.is_append_review,
        "parent_external_id": normalized.parent_external_id,
    }
    if review_id is not None:
        sample["id"] = review_id
    return sample


def _collect_jd_pages(
    *,
    source_target: SourceTarget,
    collector: BaseCollector,
    target: CollectorTarget,
    pages: int,
    limit: int,
    persist: bool,
    task: CollectionTask | None = None,
    run: CollectionRun | None = None,
) -> CollectionSummary:
    validation = collector.validate_target(target)
    if not validation.is_valid:
        raise CollectorError("; ".join(validation.errors), code="INVALID_TARGET")
    product_id = str(target.config["product_id"])
    product_page = collector.fetch_page(
        CollectionRequest(
            target=target,
            checkpoint=CollectionCheckpoint(metadata={"page_kind": "product", "product_id": product_id}),
        )
    )
    collector.parse_records(product_page)

    page_size = min(_int_config(target.config, "page_size", 10, 10), limit)
    inserted = skipped = failed = scanned = 0
    type_counts: Counter[str] = Counter()
    samples: list[dict[str, Any]] = []
    checkpoint: dict[str, Any] = {}
    start_page = int((task.last_checkpoint if task else {}).get("page", 1))

    for page in range(start_page, pages + 1):
        if task is not None:
            check_collection_stop(task.id)
        raw_page = collector.fetch_page(
            CollectionRequest(
                target=target,
                checkpoint=CollectionCheckpoint(
                    page=page,
                    metadata={
                        "page_kind": "comments",
                        "product_id": product_id,
                        "page_size": page_size,
                        "sort_mode": "CURRENT_PAGE_DEFAULT",
                    },
                ),
                limit=min(limit - scanned, page_size),
            )
        )
        if task is not None:
            _request_log(task.id, source_target.source.code, page, "", raw_page.metadata)
        raw_records = collector.parse_records(raw_page)
        main_records = [record for record in raw_records if record.record_type == "REVIEW"]
        if not main_records:
            if raw_page.metadata.get("is_last_page") is True:
                break
            raise CollectorError(
                "评论页应有数据但返回空, 可能发生访问限制或结构变化",
                code="POSSIBLE_BLOCK_OR_FORMAT_CHANGE",
            )

        remaining_main = limit - scanned
        allowed_main_ids = {record.external_id for record in main_records[:remaining_main]}
        allowed_comment_ids = {str(value).removeprefix("jd_review:") for value in allowed_main_ids}
        page_records = [
            record
            for record in raw_records
            if (record.record_type == "REVIEW" and record.external_id in allowed_main_ids)
            or (record.record_type == "APPEND_REVIEW" and record.payload.get("comment_id") in allowed_comment_ids)
        ]
        scanned += min(len(main_records), remaining_main)
        last_comment_id = ""
        for raw_record in page_records:
            normalized = collector.normalize_record(raw_record)
            if normalized.record_type == "REVIEW":
                last_comment_id = str(normalized.external_id or "").removeprefix("jd_review:")
            if persist:
                result = persist_review(source_target, normalized)
                if result.inserted:
                    inserted += 1
                    type_counts[normalized.record_type] += 1
                    if len(samples) < 10:
                        samples.append(_sample_review(normalized, result.review.id))
                else:
                    skipped += 1
            else:
                type_counts[normalized.record_type] += 1
                if len(samples) < 10:
                    samples.append(_sample_review(normalized))

        checkpoint = {
            "page": page,
            "page_size": page_size,
            "last_comment_id": last_comment_id,
            "sort_mode": "CURRENT_PAGE_DEFAULT",
        }
        if task is not None and run is not None:
            _save_progress(
                task.id,
                run.id,
                inserted=inserted,
                skipped=skipped,
                failed=failed,
                checkpoint=checkpoint,
            )
        if scanned >= limit:
            break

    return CollectionSummary(
        scanned_threads=scanned,
        inserted_records=inserted,
        skipped_records=skipped,
        failed_records=failed,
        record_types=dict(type_counts),
        samples=samples,
    )


def run_collection(
    task_id: int,
    *,
    dispatch_token: str | UUID | None = None,
    limit_override: int | None = None,
    pages_override: int | None = None,
) -> CollectionSummary:
    if dispatch_token is None:
        with transaction.atomic():
            direct_task = CollectionTask.objects.select_for_update().get(pk=task_id)
            if direct_task.status != CollectionStatus.PENDING:
                raise DuplicateCollectionExecution(f"任务 #{task_id} 当前不可直接执行")
            direct_token = direct_task.dispatch_token or uuid4()
            direct_task.dispatch_token = direct_token
            direct_task.dispatched_at = timezone.now()
            direct_task.save(update_fields=("dispatch_token", "dispatched_at", "updated_at"))
        dispatch_token = direct_token
    try:
        task, run = _start_run(task_id, UUID(str(dispatch_token)))
    except CollectionStopRequested:
        return CollectionSummary(0, 0, 0, 0, {}, [], completed=False)
    source_target = task.source_target
    try:
        collector = get_collector(source_target.source.code)
    except Exception as exc:
        message = f"{exc.code}: {exc}" if isinstance(exc, CollectorError) else f"COLLECTION_ERROR: {exc}"
        _finish_failed(task.id, run.id, message)
        raise
    target = _build_collector_target(source_target)
    config = target.config
    if source_target.source.code == "JD":
        pages = min(max(pages_override or _int_config(config, "max_pages", 3, 3), 1), 3)
        limit = min(max(limit_override or task.requested_limit or 30, 1), 30)
        try:
            summary = _collect_jd_pages(
                source_target=source_target,
                collector=collector,
                target=target,
                pages=pages,
                limit=limit,
                persist=True,
                task=task,
                run=run,
            )
            check_collection_stop(task.id)
            _finish_success(task.id, run.id)
            return summary
        except CollectionStopRequested:
            _finish_stopped(task.id, run.id)
            return CollectionSummary(0, 0, 0, 0, {}, [], completed=False)
        except Exception as exc:
            message = f"{exc.code}: {exc}" if isinstance(exc, CollectorError) else f"COLLECTION_ERROR: {exc}"
            logger.exception("collection_failed collection_task_id=%s source=%s", task.id, source_target.source.code)
            _finish_failed(task.id, run.id, message)
            raise

    if task.task_type == CollectionTaskType.FULL:
        try:
            check_collection_stop(task.id)
            chunk = run_honor_full_chunk(
                task=task,
                source_target=source_target,
                collector=collector,
                target=target,
            )
            check_collection_stop(task.id)
            task.refresh_from_db()
            discovered = task.discovered_threads.count()
            completed_threads = task.discovered_threads.filter(status__in=("SUCCESS", "SKIPPED")).count()
            task.success_count += chunk.inserted
            task.skipped_count += chunk.duplicates
            task.failure_count += chunk.failed
            task.new_records += chunk.inserted
            task.duplicate_records += chunk.duplicates
            task.new_threads = task.discovered_threads.filter(status="SUCCESS").count()
            task.last_checkpoint = chunk.checkpoint
            task.verification_report = chunk.report
            task.completion_verified = chunk.verified
            # Never write the stale in-memory RUNNING status back over STOPPING.
            task.save(
                update_fields=(
                    "success_count",
                    "skipped_count",
                    "failure_count",
                    "new_records",
                    "duplicate_records",
                    "new_threads",
                    "last_checkpoint",
                    "verification_report",
                    "completion_verified",
                    "updated_at",
                )
            )
            run.success_count = chunk.inserted
            run.skipped_count = chunk.duplicates
            run.failure_count = chunk.failed
            run.new_threads = completed_threads
            run.new_records = chunk.inserted
            run.duplicate_records = chunk.duplicates
            run.checkpoint_json = chunk.checkpoint
            run.verification_report = chunk.report
            run.completion_verified = chunk.verified
            run.save()
            check_collection_stop(task.id)
            if chunk.continuation_required:
                _finish_continuation(task.id, run.id)
            elif chunk.verified:
                _finish_success(task.id, run.id, verified=True, report=chunk.report)
            else:
                unresolved = ", ".join(chunk.report.get("unresolved_thread_ids", [])[:20])
                _finish_failed(task.id, run.id, f"FULL_VERIFICATION_FAILED: unresolved={unresolved}")
            return CollectionSummary(
                scanned_threads=discovered,
                inserted_records=chunk.inserted,
                skipped_records=chunk.duplicates,
                failed_records=chunk.failed,
                record_types={},
                samples=[],
                new_threads=task.new_threads,
                new_records=chunk.inserted,
                duplicate_records=chunk.duplicates,
                completed=not chunk.continuation_required,
                continuation_required=chunk.continuation_required,
                completion_verified=chunk.verified,
                verification_report=chunk.report,
            )
        except CollectionStopRequested:
            _finish_stopped(task.id, run.id)
            return CollectionSummary(0, 0, 0, 0, {}, [], completed=False)
        except Exception as exc:
            message = f"{exc.code}: {exc}" if isinstance(exc, CollectorError) else f"COLLECTION_ERROR: {exc}"
            logger.exception("full_collection_failed collection_task_id=%s", task.id)
            _finish_failed(task.id, run.id, message)
            raise

    max_pages = min(_int_config(config, "max_topic_pages", 5, 10), task.requested_pages or 10)
    configured_threads = _int_config(config, "max_threads", 100, 200)
    requested_limit = limit_override or task.requested_limit or configured_threads
    max_threads = min(max(int(requested_limit), 1), configured_threads, 200)
    checkpoint: dict[str, Any] = {}
    start_page = 1
    start_index = 0
    inserted = skipped = failed = scanned = duplicate_records = 0
    new_threads = known_threads = 0
    stopped_at_known_boundary = False
    type_counts: Counter[str] = Counter()
    samples: list[dict[str, Any]] = []

    try:
        for topic_page in range(start_page, max_pages + 1):
            check_collection_stop(task.id)
            topic_request = CollectionRequest(
                target=target,
                checkpoint=CollectionCheckpoint(
                    page=topic_page,
                    metadata={"page_kind": "topic", "topic_id": config.get("topic_id", 595)},
                ),
                limit=max_threads,
            )
            raw_topic = collector.fetch_page(topic_request)
            _request_log(task.id, source_target.source.code, topic_page, "", raw_topic.metadata)
            thread_links = collector.parse_records(raw_topic)
            if not thread_links:
                checkpoint = {"topic_page": topic_page, "thread_index": 0, "completed": True}
                _save_progress(
                    task.id,
                    run.id,
                    inserted=inserted,
                    skipped=skipped,
                    failed=failed,
                    checkpoint=checkpoint,
                    progress_stats={
                        "new_threads": new_threads,
                        "known_threads": known_threads,
                        "new_records": inserted,
                        "duplicate_records": duplicate_records,
                        "stopped_at_known_boundary": stopped_at_known_boundary,
                    },
                )
                break
            page_start_index = start_index if topic_page == start_page else 0

            for thread_index, thread_link in enumerate(thread_links[page_start_index:], start=page_start_index):
                check_collection_stop(task.id)
                if scanned >= max_threads:
                    break
                scanned += 1
                listing_data = dict(thread_link.payload)
                thread_id = str(listing_data["thread_id"])
                thread_external_id = f"thread:{thread_id}"
                thread_was_known = ReviewRecord.objects.filter(
                    source_id=source_target.source_id,
                    record_type="THREAD",
                    external_id=thread_external_id,
                ).exists()
                if thread_was_known:
                    known_threads += 1
                thread_url = str(listing_data["thread_url"])
                thread_target = _build_collector_target(source_target, target_url=thread_url)
                thread_request = CollectionRequest(
                    target=thread_target,
                    checkpoint=CollectionCheckpoint(
                        metadata={
                            "page_kind": "thread",
                            "thread_id": thread_id,
                            "listing_data": listing_data,
                        }
                    ),
                )
                raw_thread = collector.fetch_page(thread_request)
                _request_log(task.id, source_target.source.code, topic_page, thread_id, raw_thread.metadata)
                first_html = (
                    raw_thread.content.decode("utf-8", errors="replace")
                    if isinstance(raw_thread.content, bytes)
                    else raw_thread.content
                )
                if not is_valid_thread_page(first_html):
                    raise CollectorError(f"帖子 {thread_id} 返回异常页面", code="INVALID_THREAD_PAGE")
                raw_records = collector.parse_records(raw_thread)
                if not raw_records:
                    raise CollectorError(f"帖子 {thread_id} 未解析出记录", code="EMPTY_THREAD")
                reply_pages = extract_thread_page_count(first_html, thread_id=thread_id)
                for reply_page in range(2, reply_pages + 1):
                    check_collection_stop(task.id)
                    paged_request = CollectionRequest(
                        target=thread_target,
                        checkpoint=CollectionCheckpoint(
                            page=reply_page,
                            metadata={
                                "page_kind": "thread",
                                "thread_id": thread_id,
                                "listing_data": listing_data,
                            },
                        ),
                    )
                    raw_reply_page = collector.fetch_page(paged_request)
                    reply_html = (
                        raw_reply_page.content.decode("utf-8", errors="replace")
                        if isinstance(raw_reply_page.content, bytes)
                        else raw_reply_page.content
                    )
                    if not is_valid_thread_page(reply_html):
                        raise CollectorError(
                            f"帖子 {thread_id} 第 {reply_page} 页返回异常页面",
                            code="INVALID_THREAD_PAGE",
                        )
                    paged_records = collector.parse_records(raw_reply_page)
                    if not paged_records:
                        raise CollectorError(
                            f"帖子 {thread_id} 第 {reply_page} 页无记录",
                            code="EMPTY_THREAD_PAGE",
                        )
                    raw_records.extend(paged_records[1:])

                thread_payload = raw_records[0].payload
                raw_data = thread_payload.get("raw_data", {})
                topic_tags = raw_data.get("topic_tags", []) if isinstance(raw_data, dict) else []
                aliases = target.config.get("product_aliases", [])
                if not is_product_related(
                    title=str(thread_payload.get("title", "")),
                    content=str(thread_payload.get("content", "")),
                    topic_tags=[str(value) for value in topic_tags] if isinstance(topic_tags, list) else [],
                    aliases=[str(value) for value in aliases] if isinstance(aliases, list) else [],
                    excluded_aliases=[str(value) for value in target.config.get("excluded_product_aliases", [])],
                ):
                    skipped += 1
                    checkpoint = {
                        "topic_page": topic_page,
                        "thread_index": thread_index + 1,
                        "last_thread_id": thread_id,
                        "skip_reason": "PRODUCT_NOT_MATCHED",
                    }
                    _save_progress(
                        task.id,
                        run.id,
                        inserted=inserted,
                        skipped=skipped,
                        failed=failed,
                        checkpoint=checkpoint,
                        progress_stats={
                            "new_threads": new_threads,
                            "known_threads": known_threads,
                            "new_records": inserted,
                            "duplicate_records": duplicate_records,
                            "stopped_at_known_boundary": False,
                        },
                    )
                    continue

                for raw_record in raw_records:
                    normalized = collector.normalize_record(raw_record)
                    result = persist_review(source_target, normalized)
                    if result.inserted:
                        inserted += 1
                        if normalized.record_type == "THREAD":
                            new_threads += 1
                        type_counts[normalized.record_type] += 1
                        if len(samples) < 10:
                            samples.append(
                                {
                                    "id": result.review.id,
                                    "record_type": normalized.record_type,
                                    "title": normalized.title,
                                    "content_preview": normalized.content[:80],
                                    "published_at": normalized.published_at.isoformat()
                                    if normalized.published_at
                                    else None,
                                    "author_role": normalized.author_role,
                                    "is_official": normalized.is_official,
                                    "source_url": normalized.source_url,
                                    "parent_external_id": normalized.parent_external_id,
                                }
                            )
                    else:
                        skipped += 1
                        duplicate_records += 1

                checkpoint = {
                    "topic_page": topic_page,
                    "thread_index": thread_index + 1,
                    "last_thread_id": thread_id,
                }
                _save_progress(
                    task.id,
                    run.id,
                    inserted=inserted,
                    skipped=skipped,
                    failed=failed,
                    checkpoint=checkpoint,
                    progress_stats={
                        "new_threads": new_threads,
                        "known_threads": known_threads,
                        "new_records": inserted,
                        "duplicate_records": duplicate_records,
                        "stopped_at_known_boundary": False,
                    },
                )
                logger.info(
                    "collection_thread collection_task_id=%s source=%s topic_page=%s thread_id=%s "
                    "parsed_records=%s inserted_records=%s skipped_records=%s checkpoint=%s",
                    task.id,
                    source_target.source.code,
                    topic_page,
                    thread_id,
                    len(raw_records),
                    inserted,
                    skipped,
                    checkpoint,
                )
            if scanned >= max_threads:
                break
            checkpoint = {"topic_page": topic_page + 1, "thread_index": 0}
            _save_progress(
                task.id,
                run.id,
                inserted=inserted,
                skipped=skipped,
                failed=failed,
                checkpoint=checkpoint,
                progress_stats={
                    "new_threads": new_threads,
                    "known_threads": known_threads,
                    "new_records": inserted,
                    "duplicate_records": duplicate_records,
                    "stopped_at_known_boundary": stopped_at_known_boundary,
                },
            )
        _finish_success(task.id, run.id)
    except CollectionStopRequested:
        _finish_stopped(task.id, run.id)
        return CollectionSummary(0, 0, 0, 0, {}, [], completed=False)
    except Exception as exc:
        if isinstance(exc, CollectorError):
            message = f"{exc.code}: {exc}"
        else:
            message = f"COLLECTION_ERROR: {exc}"
        logger.exception("collection_failed collection_task_id=%s source=%s", task.id, source_target.source.code)
        _finish_failed(task.id, run.id, message)
        raise

    return CollectionSummary(
        scanned_threads=scanned,
        inserted_records=inserted,
        skipped_records=skipped,
        failed_records=failed,
        record_types=dict(type_counts),
        samples=samples,
        new_threads=new_threads,
        known_threads=known_threads,
        new_records=inserted,
        duplicate_records=duplicate_records,
        stopped_at_known_boundary=stopped_at_known_boundary,
    )


def preview_target(source_target: SourceTarget, *, limit: int = 1, pages: int = 1) -> CollectionSummary:
    collector = get_collector(source_target.source.code)
    target = _build_collector_target(source_target)
    safe_limit = min(max(limit, 1), 10)
    if source_target.source.code == "JD":
        return _collect_jd_pages(
            source_target=source_target,
            collector=collector,
            target=target,
            pages=min(max(pages, 1), 3),
            limit=min(max(limit, 1), 30),
            persist=False,
        )
    raw_topic = collector.fetch_page(
        CollectionRequest(
            target=target,
            checkpoint=CollectionCheckpoint(
                page=1,
                metadata={"page_kind": "topic", "topic_id": target.config.get("topic_id", 595)},
            ),
            limit=safe_limit,
        )
    )
    links = collector.parse_records(raw_topic)[:safe_limit]
    type_counts: Counter[str] = Counter()
    samples: list[dict[str, Any]] = []
    parsed_count = 0
    for link in links:
        listing_data = dict(link.payload)
        thread_id = str(listing_data["thread_id"])
        thread_target = _build_collector_target(source_target, target_url=str(listing_data["thread_url"]))
        raw_thread = collector.fetch_page(
            CollectionRequest(
                target=thread_target,
                checkpoint=CollectionCheckpoint(
                    metadata={"page_kind": "thread", "thread_id": thread_id, "listing_data": listing_data}
                ),
            )
        )
        for raw_record in collector.parse_records(raw_thread):
            normalized = collector.normalize_record(raw_record)
            parsed_count += 1
            type_counts[normalized.record_type] += 1
            if len(samples) < 10:
                samples.append(
                    {
                        "external_id": normalized.external_id,
                        "record_type": normalized.record_type,
                        "title": normalized.title,
                        "content_preview": normalized.content[:80],
                        "published_at": normalized.published_at.isoformat() if normalized.published_at else None,
                        "author_role": normalized.author_role,
                        "is_official": normalized.is_official,
                        "source_url": normalized.source_url,
                        "parent_external_id": normalized.parent_external_id,
                    }
                )
    return CollectionSummary(
        scanned_threads=len(links),
        inserted_records=0,
        skipped_records=0,
        failed_records=0,
        record_types=dict(type_counts),
        samples=samples,
    )
