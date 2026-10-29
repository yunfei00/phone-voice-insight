"""Resumable Honor FULL discovery, detail collection, retry and verification."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from collectors.base import BaseCollector, CollectionCheckpoint, CollectionRequest, CollectorError, CollectorTarget
from collectors.honor_club.normalizer import is_product_related
from collectors.honor_club.parser import (
    extract_thread_page_count,
    extract_topic_page_count,
    is_valid_thread_page,
    is_valid_topic_page,
)
from django.db.models import Q

from apps.collection.models import CollectionDiscoveredThread, CollectionTask, DiscoveryStatus
from apps.collection.services.orchestration import refresh_source_lease
from apps.collection.services.review_persistence import persist_review
from apps.reviews.models import ReviewRecord
from apps.reviews.services.thread_tree import parse_human_count
from apps.sources.models import SourceTarget


@dataclass(frozen=True)
class FullChunkResult:
    checkpoint: dict[str, Any]
    inserted: int
    duplicates: int
    failed: int
    continuation_required: bool
    verified: bool
    report: dict[str, Any]


def _config_int(config: dict[str, Any], key: str, default: int, maximum: int) -> int:
    try:
        value = int(config.get(key, default))
    except (TypeError, ValueError):
        value = default
    return min(max(value, 1), maximum)



def _raw_text(page: Any) -> str:
    return page.content.decode("utf-8", errors="replace") if isinstance(page.content, bytes) else page.content


def _thread_request(target: CollectorTarget, item: CollectionDiscoveredThread, page: int) -> CollectionRequest:
    thread_target = CollectorTarget(
        source_code=target.source_code,
        product_code=target.product_code,
        target_url=item.thread_url,
        external_id=target.external_id,
        config=target.config,
    )
    return CollectionRequest(
        target=thread_target,
        checkpoint=CollectionCheckpoint(
            page=page,
            metadata={
                "page_kind": "thread",
                "thread_id": item.thread_id,
                "listing_data": item.listing_data,
            },
        ),
    )


def _collect_one_thread(
    *,
    source_target: SourceTarget,
    collector: BaseCollector,
    target: CollectorTarget,
    item: CollectionDiscoveredThread,
    execution_token: UUID,
) -> tuple[int, int, int, bool, bool]:
    inserted = duplicates = reply_pages = 0
    start_page = max(item.next_reply_page, 1)
    pages = item.expected_reply_pages
    first_page = None
    if start_page == 1:
        first_page = collector.fetch_page(_thread_request(target, item, 1))
        first_html = _raw_text(first_page)
        if not is_valid_thread_page(first_html):
            raise CollectorError(f"帖子 {item.thread_id} 返回异常页面", code="INVALID_THREAD_PAGE", retryable=True)
        pages = extract_thread_page_count(first_html, thread_id=item.thread_id)
        item.expected_reply_pages = pages
        item.save(update_fields=("expected_reply_pages", "updated_at"))
    if pages < start_page:
        return inserted, duplicates, reply_pages, True, True

    page_budget = _config_int(target.config, "full_chunk_reply_pages", 20, 100)
    end_page = min(pages, start_page + page_budget - 1)
    aliases = [str(value) for value in target.config.get("product_aliases", [])]
    excluded_aliases = [str(value) for value in target.config.get("excluded_product_aliases", [])]
    product_match = True
    for page_number in range(start_page, end_page + 1):
        raw_page = (
            first_page
            if page_number == 1 and first_page is not None
            else collector.fetch_page(_thread_request(target, item, page_number))
        )
        html = _raw_text(raw_page)
        if not is_valid_thread_page(html):
            raise CollectorError(
                f"帖子 {item.thread_id} 第 {page_number} 页返回异常页面",
                code="INVALID_THREAD_PAGE",
                retryable=True,
            )
        records = collector.parse_records(raw_page)
        if not records:
            raise CollectorError(f"帖子 {item.thread_id} 第 {page_number} 页无记录", code="EMPTY_THREAD")
        if page_number == 1:
            thread_payload = records[0].payload
            raw_data = thread_payload.get("raw_data", {})
            topic_tags = raw_data.get("topic_tags", []) if isinstance(raw_data, dict) else []
            product_match = is_product_related(
                title=str(thread_payload.get("title", "")),
                content=str(thread_payload.get("content", "")),
                topic_tags=[str(value) for value in topic_tags] if isinstance(topic_tags, list) else [],
                aliases=aliases,
                excluded_aliases=excluded_aliases,
            )
            if not product_match:
                return 0, 0, page_number, False, True
        for raw_record in records if page_number == 1 else records[1:]:
            result = persist_review(source_target, collector.normalize_record(raw_record))
            if result.inserted:
                inserted += 1
            else:
                duplicates += 1
        reply_pages += 1
        item.reply_pages_scanned += 1
        item.next_reply_page = page_number + 1
        item.save(update_fields=("reply_pages_scanned", "next_reply_page", "updated_at"))
        refresh_source_lease(item.task_id, execution_token)
    return inserted, duplicates, reply_pages, product_match, item.next_reply_page > pages


def _verification_report(task: CollectionTask, checkpoint: dict[str, Any], retry_count: int) -> dict[str, Any]:
    discovered = task.discovered_threads.count()
    success = task.discovered_threads.filter(status=DiscoveryStatus.SUCCESS).count()
    skipped = task.discovered_threads.filter(status=DiscoveryStatus.SKIPPED).count()
    blocked = list(
        task.discovered_threads.filter(status=DiscoveryStatus.BLOCKED_SKIPPED).values(
            "thread_id", "thread_url", "attempts", "last_error"
        )
    )
    failed_items = list(
        task.discovered_threads.filter(status=DiscoveryStatus.FAILED).values_list("thread_id", flat=True)
    )
    failed_details = list(
        task.discovered_threads.filter(status=DiscoveryStatus.FAILED).values(
            "thread_id", "thread_url", "attempts", "last_error", "next_reply_page"
        )
    )
    pending = task.discovered_threads.filter(status=DiscoveryStatus.PENDING).count()
    reply_pages = sum(task.discovered_threads.values_list("reply_pages_scanned", flat=True))
    source_replies = sum(
        value or 0 for value in task.discovered_threads.values_list("source_reported_reply_count", flat=True)
    )
    collected_replies = sum(task.discovered_threads.values_list("collected_reply_count", flat=True))
    discrepancies = (
        task.discovered_threads.filter(
            status=DiscoveryStatus.SUCCESS,
            source_reported_reply_count__isnull=False,
        )
        .exclude(source_reported_reply_count=models_collected_reply_count())
        .count()
    )
    expected_pages = int(checkpoint.get("expected_topic_pages", 0))
    scanned_pages = int(checkpoint.get("scanned_topic_pages", 0))
    verified = (
        expected_pages > 0
        and scanned_pages == expected_pages
        and discovered == success + skipped + len(blocked)
        and not failed_items
        and pending == 0
    )
    warnings: list[str] = []
    if discrepancies:
        warnings.append("来源回复数与已采集回复数存在差异；该指标仅诊断，不作为失败条件。")  # noqa: RUF001
    return {
        "expected_topic_pages": expected_pages,
        "scanned_topic_pages": scanned_pages,
        "discovered_threads": discovered,
        "product_matched_threads": success,
        "product_skipped_threads": skipped,
        "access_blocked_skipped_threads": len(blocked),
        "access_blocked_thread_details": blocked,
        "accessible_scope_verified": verified,
        "thread_details_success": success,
        "thread_details_failed": len(failed_items),
        "reply_pages_scanned": reply_pages,
        "source_reported_reply_count": source_replies,
        "collected_reply_count": collected_replies,
        "reply_count_discrepancies": discrepancies,
        "retry_count": retry_count,
        "unresolved_thread_ids": failed_items,
        "unresolved_thread_details": failed_details,
        "unresolved_pages": [],
        "completion_verified": verified,
        "verification_warnings": warnings,
    }


def models_collected_reply_count() -> Any:
    """F-expression kept in a helper so report code stays readable."""

    from django.db.models import F

    return F("collected_reply_count")


def run_honor_full_chunk(
    *,
    task: CollectionTask,
    source_target: SourceTarget,
    collector: BaseCollector,
    target: CollectorTarget,
) -> FullChunkResult:
    from apps.collection.services.collection_runner import check_collection_stop

    check_collection_stop(task.id)
    if task.execution_token is None:
        raise RuntimeError("采集任务缺少执行代次令牌")
    execution_token = task.execution_token
    checkpoint = dict(task.last_checkpoint or {})
    phase = str(checkpoint.get("phase", "discovery"))
    inserted = duplicates = failed = 0
    retry_count = int(checkpoint.get("retry_count", 0))
    config = target.config

    if phase == "discovery":
        next_page = int(checkpoint.get("next_topic_page", 1))
        page_chunk = _config_int(config, "full_chunk_topic_pages", 10, 100)
        expected_pages = int(checkpoint.get("expected_topic_pages", 0))
        page_count_reliable = bool(checkpoint.get("topic_page_count_reliable", False))
        scanned_pages = int(checkpoint.get("scanned_topic_pages", 0))
        fallback_limit = _config_int(config, "full_fallback_max_topic_pages", 1000, 10000)
        for page_number in range(next_page, next_page + page_chunk):
            check_collection_stop(task.id)
            raw_page = collector.fetch_page(
                CollectionRequest(
                    target=target,
                    checkpoint=CollectionCheckpoint(
                        page=page_number,
                        metadata={"page_kind": "topic", "topic_id": config.get("topic_id", 595)},
                    ),
                )
            )
            refresh_source_lease(task.id, execution_token)
            html = _raw_text(raw_page)
            if not is_valid_topic_page(html):
                raise CollectorError(
                    f"话题第 {page_number} 页不是有效内容页", code="INVALID_TOPIC_PAGE", retryable=True
                )
            if page_number == 1:
                expected_pages = extract_topic_page_count(html, topic_id=int(config.get("topic_id", 595)))
            records = collector.parse_records(raw_page)
            if page_number == 1:
                page_count_reliable = expected_pages > 1 or not records
                if not page_count_reliable:
                    expected_pages = 0
            if not records and page_count_reliable and page_number <= expected_pages:
                if page_number == 1 and expected_pages == 1:
                    scanned_pages = 1
                    checkpoint.update(
                        {
                            "phase": "collection",
                            "expected_topic_pages": 1,
                            "scanned_topic_pages": 1,
                            "topic_page_count_reliable": True,
                        }
                    )
                    phase = "collection"
                    break
                raise CollectorError(f"话题第 {page_number} 页应有帖子但解析为空", code="EMPTY_TOPIC_PAGE")
            if not records and not page_count_reliable:
                expected_pages = scanned_pages
                checkpoint.update(
                    {
                        "phase": "collection",
                        "expected_topic_pages": expected_pages,
                        "scanned_topic_pages": scanned_pages,
                        "topic_page_count_reliable": False,
                    }
                )
                phase = "collection"
                break
            created_on_page = 0
            for position, record in enumerate(records):
                data = dict(record.payload)
                _, created = CollectionDiscoveredThread.objects.update_or_create(
                    task=task,
                    thread_id=str(data["thread_id"]),
                    defaults={
                        "topic_page": page_number,
                        "position": position,
                        "thread_url": str(data["thread_url"]),
                        "listing_data": data,
                    },
                )
                created_on_page += int(created)
            if not page_count_reliable and page_number > 1 and created_on_page == 0:
                expected_pages = scanned_pages
                checkpoint.update(
                    {
                        "phase": "collection",
                        "expected_topic_pages": expected_pages,
                        "scanned_topic_pages": scanned_pages,
                        "topic_page_count_reliable": False,
                    }
                )
                phase = "collection"
                break
            scanned_pages = page_number
            checkpoint.update(
                {
                    "phase": "discovery",
                    "next_topic_page": page_number + 1,
                    "expected_topic_pages": expected_pages,
                    "scanned_topic_pages": scanned_pages,
                    "topic_page_count_reliable": page_count_reliable,
                }
            )
            if page_count_reliable and page_number >= expected_pages:
                checkpoint.update({"phase": "collection", "current_thread_id": ""})
                phase = "collection"
                break
            if not page_count_reliable and page_number >= fallback_limit:
                raise CollectorError(
                    f"话题页数无法可靠解析; 扫描达到安全上限 {fallback_limit}",
                    code="TOPIC_PAGE_LIMIT",
                )
        if phase == "discovery":
            return FullChunkResult(checkpoint, inserted, duplicates, failed, True, False, {})

    if phase in ("collection", "retry"):
        # Finish the first pass before retrying failed threads.
        max_attempts = _config_int(config, "full_thread_max_attempts", 4, 5)
        chunk_size = _config_int(config, "full_chunk_threads", 20, 100)
        if phase == "collection":
            candidates_query = task.discovered_threads.filter(status=DiscoveryStatus.PENDING)
        else:
            candidates_query = task.discovered_threads.filter(
                status=DiscoveryStatus.FAILED, attempts__lt=max_attempts
            )
        candidates = list(candidates_query.order_by("attempts", "topic_page", "position")[:chunk_size])
        for item in candidates:
            check_collection_stop(task.id)
            checkpoint["current_thread_id"] = item.thread_id
            was_retry = item.status == DiscoveryStatus.FAILED
            try:
                new_count, duplicate_count, _reply_pages, matched, completed = _collect_one_thread(
                    source_target=source_target,
                    collector=collector,
                    target=target,
                    item=item,
                    execution_token=execution_token,
                )
                inserted += new_count
                duplicates += duplicate_count
                if not completed:
                    item.status = DiscoveryStatus.PENDING
                elif matched:
                    item.status = DiscoveryStatus.SUCCESS
                    item.source_reported_reply_count = parse_human_count(item.listing_data.get("reply_count"))
                    item.collected_reply_count = ReviewRecord.objects.filter(
                        source=source_target.source,
                        product=source_target.product,
                        record_type__in=("REPLY", "OFFICIAL_REPLY"),
                        raw_data__thread_id=item.thread_id,
                    ).count()
                else:
                    item.status = DiscoveryStatus.SKIPPED
                item.last_error = ""
            except Exception as exc:
                item.attempts += 1
                error_code = str(getattr(exc, "code", "COLLECTION_ERROR")).upper()
                # Only explicit access-control responses qualify for a verified skip.
                blocked_codes = {
                    "HTTP_401", "HTTP_403", "AUTH_REQUIRED", "LOGIN_REQUIRED",
                    "LOGIN_WALL", "PERMISSION_DENIED", "ACCESS_DENIED", "BLOCKED_PERMISSION_PAGE",
                }
                item.status = (
                    DiscoveryStatus.BLOCKED_SKIPPED
                    if error_code in blocked_codes and item.attempts >= max_attempts
                    else DiscoveryStatus.FAILED
                )
                item.last_error = f"{error_code}: {exc}"
                failed += 1
            item.save()
            if was_retry:
                retry_count += 1
            checkpoint["retry_count"] = retry_count
        checkpoint["current_thread_id"] = ""
        if task.discovered_threads.filter(status=DiscoveryStatus.PENDING).exists():
            return FullChunkResult(checkpoint, inserted, duplicates, failed, True, False, {})
        if task.discovered_threads.filter(
            status=DiscoveryStatus.FAILED, attempts__lt=max_attempts
        ).exists():
            checkpoint["phase"] = "retry"
            return FullChunkResult(checkpoint, inserted, duplicates, failed, True, False, {})
        checkpoint["phase"] = "verification"

    report = _verification_report(task, checkpoint, retry_count)
    return FullChunkResult(
        checkpoint={**checkpoint, "phase": "completed", "completed": True},
        inserted=inserted,
        duplicates=duplicates,
        failed=failed,
        continuation_required=False,
        verified=bool(report["completion_verified"]),
        report=report,
    )
