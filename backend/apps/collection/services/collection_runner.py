"""采集任务编排、checkpoint 与统计。"""

from __future__ import annotations

import logging
from collections import Counter
from dataclasses import dataclass
from typing import Any

from collectors.base import (
    BaseCollector,
    CollectionCheckpoint,
    CollectionRequest,
    CollectorError,
    CollectorTarget,
    NormalizedReview,
)
from collectors.honor_club.normalizer import is_power2_related
from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from apps.collection.models import CollectionRun, CollectionStatus, CollectionTask
from apps.collection.services.collector_registry import get_collector
from apps.collection.services.review_persistence import persist_review
from apps.products.models import ProductAlias
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
    return CollectorTarget(
        source_code=source_target.source.code,
        product_code=source_target.product.normalized_name,
        target_url=target_url or source_target.target_url,
        external_id=source_target.external_id,
        config=config,
    )


def _start_run(task_id: int) -> tuple[CollectionTask, CollectionRun]:
    with transaction.atomic():
        task = (
            CollectionTask.objects.select_for_update()
            .select_related("source_target__source", "source_target__product")
            .get(pk=task_id)
        )
        task.transition_to(CollectionStatus.RUNNING)
        started_at = timezone.now()
        task.started_at = started_at
        task.finished_at = None
        task.success_count = 0
        task.skipped_count = 0
        task.failure_count = 0
        task.error_message = ""
        task.save(
            update_fields=(
                "status",
                "started_at",
                "finished_at",
                "success_count",
                "skipped_count",
                "failure_count",
                "error_message",
                "updated_at",
            )
        )
        latest_run = task.runs.aggregate(max_number=Max("run_number"))["max_number"] or 0
        run = CollectionRun.objects.create(
            task=task,
            run_number=latest_run + 1,
            status=CollectionStatus.RUNNING,
            started_at=started_at,
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
) -> None:
    with transaction.atomic():
        task = CollectionTask.objects.select_for_update().get(pk=task_id)
        task.success_count = inserted
        task.skipped_count = skipped
        task.failure_count = failed
        task.last_checkpoint = checkpoint
        task.save(
            update_fields=(
                "success_count",
                "skipped_count",
                "failure_count",
                "last_checkpoint",
                "updated_at",
            )
        )
        run = CollectionRun.objects.select_for_update().get(pk=run_id)
        run.success_count = inserted
        run.skipped_count = skipped
        run.failure_count = failed
        run.checkpoint_json = checkpoint
        run.save(update_fields=("success_count", "skipped_count", "failure_count", "checkpoint_json"))


def _finish_success(task_id: int, run_id: int) -> None:
    finished_at = timezone.now()
    with transaction.atomic():
        task = CollectionTask.objects.select_for_update().get(pk=task_id)
        task.transition_to(CollectionStatus.SUCCESS)
        task.finished_at = finished_at
        task.save(update_fields=("status", "finished_at", "updated_at"))
        run = CollectionRun.objects.select_for_update().get(pk=run_id)
        run.status = CollectionStatus.SUCCESS
        run.finished_at = finished_at
        run.save(update_fields=("status", "finished_at"))


def _finish_failed(task_id: int, run_id: int, message: str) -> None:
    finished_at = timezone.now()
    with transaction.atomic():
        task = CollectionTask.objects.select_for_update().get(pk=task_id)
        task.transition_to(CollectionStatus.FAILED)
        task.finished_at = finished_at
        task.failure_count += 1
        task.error_message = message
        task.save(update_fields=("status", "finished_at", "failure_count", "error_message", "updated_at"))
        run = CollectionRun.objects.select_for_update().get(pk=run_id)
        run.status = CollectionStatus.FAILED
        run.finished_at = finished_at
        run.failure_count = task.failure_count
        run.error_message = message
        run.save(update_fields=("status", "finished_at", "failure_count", "error_message"))


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
    limit_override: int | None = None,
    pages_override: int | None = None,
) -> CollectionSummary:
    task, run = _start_run(task_id)
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
            _finish_success(task.id, run.id)
            return summary
        except Exception as exc:
            message = f"{exc.code}: {exc}" if isinstance(exc, CollectorError) else f"COLLECTION_ERROR: {exc}"
            logger.exception("collection_failed collection_task_id=%s source=%s", task.id, source_target.source.code)
            _finish_failed(task.id, run.id, message)
            raise

    max_pages = _int_config(config, "max_topic_pages", 1, 2)
    configured_threads = _int_config(config, "max_threads", 10, 20)
    requested_limit = limit_override or task.requested_limit or configured_threads
    max_threads = min(max(int(requested_limit), 1), configured_threads, 20)
    checkpoint = dict(task.last_checkpoint or {})
    start_page = int(checkpoint.get("topic_page", 1))
    start_index = int(checkpoint.get("thread_index", 0))
    inserted = skipped = failed = scanned = 0
    type_counts: Counter[str] = Counter()
    samples: list[dict[str, Any]] = []

    try:
        for topic_page in range(start_page, max_pages + 1):
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
            page_start_index = start_index if topic_page == start_page else 0

            for thread_index, thread_link in enumerate(thread_links[page_start_index:], start=page_start_index):
                if scanned >= max_threads:
                    break
                scanned += 1
                listing_data = dict(thread_link.payload)
                thread_id = str(listing_data["thread_id"])
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
                raw_records = collector.parse_records(raw_thread)
                if not raw_records:
                    raise CollectorError(f"帖子 {thread_id} 未解析出记录", code="EMPTY_THREAD")

                thread_payload = raw_records[0].payload
                raw_data = thread_payload.get("raw_data", {})
                topic_tags = raw_data.get("topic_tags", []) if isinstance(raw_data, dict) else []
                aliases = target.config.get("product_aliases", [])
                if not is_power2_related(
                    title=str(thread_payload.get("title", "")),
                    content=str(thread_payload.get("content", "")),
                    topic_tags=[str(value) for value in topic_tags] if isinstance(topic_tags, list) else [],
                    aliases=[str(value) for value in aliases] if isinstance(aliases, list) else [],
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
                    )
                    continue

                for raw_record in raw_records:
                    normalized = collector.normalize_record(raw_record)
                    result = persist_review(source_target, normalized)
                    if result.inserted:
                        inserted += 1
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
            )
        _finish_success(task.id, run.id)
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
