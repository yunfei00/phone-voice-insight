"""Celery entry points for bounded structured analysis batches."""

from __future__ import annotations

import logging
import time
from decimal import Decimal
from typing import Any

from celery import shared_task
from django.utils import timezone

from apps.accounts.ai_service import get_user_ai_provider
from apps.analysis.models import AnalysisBatch, AnalysisBatchStatus, StructuredRunStatus
from apps.analysis.services.analysis_runner import error_counts, run_analysis_batch
from apps.analysis.services.structured_engine import analyze_content
from apps.reviews.models import AnalysisCorpusItem

logger = logging.getLogger(__name__)


@shared_task(name="run_analysis_batch_task", autoretry_for=(), max_retries=0)
def run_analysis_batch_task(
    batch_id: int,
    corpus_item_ids: list[int],
    *,
    force: bool = False,
    retry_failed: bool = False,
) -> dict[str, Any]:
    batch = AnalysisBatch.objects.get(pk=batch_id)
    item_map = {
        item.id: item
        for item in AnalysisCorpusItem.objects.filter(id__in=corpus_item_ids).select_related(
            "review", "quality", "product", "source"
        )
    }
    items = [item_map[item_id] for item_id in corpus_item_ids if item_id in item_map]
    outcomes = run_analysis_batch(batch, corpus_items=items, force=force, retry_failed=retry_failed)
    return {
        "batch_id": batch.id,
        "status": batch.status,
        "success": batch.success_count,
        "failed": batch.failed_count,
        "skipped": batch.skipped_count,
        "errors": error_counts(outcomes),
    }


@shared_task(name="run_structured_analysis_batch_task", autoretry_for=(), max_retries=0)
def run_structured_analysis_batch_task(
    batch_id: int, content_ids: list[int], *, max_retries: int = 1
) -> dict[str, Any]:
    batch = AnalysisBatch.objects.select_related("created_by").get(pk=batch_id)
    if batch.created_by is None:
        batch.status = AnalysisBatchStatus.FAILED
        batch.error_message = "BATCH_OWNER_MISSING"
        batch.save()
        return {"batch_id": batch_id, "status": batch.status}
    batch.status = AnalysisBatchStatus.RUNNING
    batch.started_at = timezone.now()
    batch.save()
    try:
        provider = get_user_ai_provider(batch.created_by)
    except Exception as exc:
        batch.status = AnalysisBatchStatus.FAILED
        batch.error_message = f"{type(exc).__name__}: {exc}"[:1000]
        batch.finished_at = timezone.now()
        batch.save(update_fields=("status", "error_message", "finished_at", "updated_at"))
        return {"batch_id": batch.id, "status": batch.status, "success": 0, "failed": len(content_ids)}
    next_allowed = time.monotonic()
    for content_id in content_ids:
        batch.refresh_from_db(fields=("status", "actual_cost", "total_tokens"))
        if batch.status in (AnalysisBatchStatus.CANCELLED, AnalysisBatchStatus.PAUSED):
            break
        if batch.token_limit and (batch.total_tokens or 0) >= batch.token_limit:
            batch.status = AnalysisBatchStatus.BUDGET_EXCEEDED
            break
        if batch.cost_budget is not None and batch.actual_cost >= batch.cost_budget:
            batch.status = AnalysisBatchStatus.BUDGET_EXCEEDED
            break
        wait_seconds = next_allowed - time.monotonic()
        if wait_seconds > 0:
            time.sleep(wait_seconds)
        try:
            run = analyze_content(content_id, provider, max_retries=max_retries, batch_id=batch.id)
        except Exception as exc:
            logger.exception("structured_analysis_item_failed batch_id=%s content_id=%s", batch.id, content_id)
            batch.failed_count += 1
            batch.error_message = f"{type(exc).__name__}: {exc}"[:1000]
            batch.save(update_fields=("failed_count", "error_message", "updated_at"))
            continue
        next_allowed = time.monotonic() + 60 / batch.requests_per_minute
        if run.status in (StructuredRunStatus.SUCCEEDED, StructuredRunStatus.REVIEW_REQUIRED):
            batch.success_count += 1
            batch.review_required_count += int(run.status == StructuredRunStatus.REVIEW_REQUIRED)
        elif run.status == StructuredRunStatus.FAILED:
            batch.failed_count += 1
        else:
            batch.skipped_count += 1
        batch.prompt_tokens = (batch.prompt_tokens or 0) + (run.input_tokens or 0)
        batch.completion_tokens = (batch.completion_tokens or 0) + (run.output_tokens or 0)
        batch.total_tokens = (batch.prompt_tokens or 0) + (batch.completion_tokens or 0)
        batch.actual_cost += (
            Decimal(run.input_tokens or 0) * batch.input_cost_per_million
            + Decimal(run.output_tokens or 0) * batch.output_cost_per_million
        ) / Decimal(1_000_000)
        batch.save()
    if batch.status == AnalysisBatchStatus.RUNNING:
        batch.status = AnalysisBatchStatus.PARTIAL if batch.failed_count else AnalysisBatchStatus.SUCCESS
    batch.finished_at = timezone.now()
    batch.save()
    dispatch_pending_structured_reviews.delay(batch.created_by_id, batch.product_id)
    return {"batch_id": batch.id, "status": batch.status, "success": batch.success_count, "failed": batch.failed_count}


@shared_task(name="dispatch_pending_structured_reviews")
def dispatch_pending_structured_reviews(user_id: int | None = None, product_id: int | None = None) -> dict[str, int]:
    """Queue one bounded chunk per invocation; Celery Beat can call this periodically.

    Successful and failed current runs are excluded from automatic dispatch. Failures
    require an explicit retry after configuration or model issues are resolved.
    """
    from django.contrib.auth.models import User
    from django.core.cache import cache

    from apps.analysis.models import AnalysisRun
    from apps.reviews.services.final_corpus import final_corpus_reviews

    lock_key = f"structured-dispatch:{user_id or 'auto'}:{product_id or 'all'}"
    if not cache.add(lock_key, "1", timeout=240):
        return {"queued": 0, "locked": 1}
    try:
        users = (
            User.objects.filter(pk=user_id)
            if user_id
            else User.objects.filter(ai_configuration__is_active=True).order_by("pk")
        )
        for user in users:
            try:
                provider = get_user_ai_provider(user)
            except Exception as exc:
                if user_id:
                    return {"queued": 0, "error_code": "AI_NOT_CONFIGURED", "detail": str(exc)[:200]}
                continue
            active = AnalysisBatch.objects.filter(
                created_by=user,
                prompt_version="structured_analysis_v1",
                status__in=(AnalysisBatchStatus.PENDING, AnalysisBatchStatus.RUNNING),
            )
            if active.exists():
                if user_id:
                    return {"queued": 0, "active_batch_id": active.first().id}
                continue
            completed = AnalysisRun.objects.filter(
                is_current=True,
                status__in=(StructuredRunStatus.SUCCEEDED, StructuredRunStatus.REVIEW_REQUIRED),
            ).values("content_id")
            failed = AnalysisRun.objects.filter(
                is_current=True,
                status=StructuredRunStatus.FAILED,
                provider=provider.provider_name,
                model=provider.model,
            ).values("content_id")
            corpus = final_corpus_reviews().exclude(pk__in=completed).exclude(pk__in=failed)
            if product_id is not None:
                corpus = corpus.filter(product_id=product_id)
            first = corpus.order_by("id").first()
            if first is None:
                continue
            ids = list(
                corpus.filter(product_id=first.product_id, source_id=first.source_id)
                .order_by("id")
                .values_list("id", flat=True)[:100]
            )
            batch = AnalysisBatch.objects.create(
                created_by=user,
                product_id=first.product_id,
                source_id=first.source_id,
                corpus_version="structured-v1",
                provider=provider.provider_name,
                model_name=provider.model,
                prompt_version="structured_analysis_v1",
                requested_count=len(ids),
                dry_run=False,
                max_concurrency=1,
                requests_per_minute=10,
                status=AnalysisBatchStatus.PENDING,
                total_tokens=0,
            )
            try:
                task = run_structured_analysis_batch_task.delay(batch.id, ids)
            except Exception as exc:
                batch.status = AnalysisBatchStatus.FAILED
                batch.error_message = f"TASK_DISPATCH_FAILED: {type(exc).__name__}: {exc}"[:1000]
                batch.finished_at = timezone.now()
                batch.save(update_fields=("status", "error_message", "finished_at", "updated_at"))
                logger.exception("structured_dispatch_failed batch_id=%s", batch.id)
                return {"queued": 0, "batch_id": batch.id, "error_code": "TASK_DISPATCH_FAILED"}
            return {"queued": len(ids), "batch_id": batch.id, "celery_task_id": task.id}
        return {"queued": 0}
    finally:
        cache.delete(lock_key)


@shared_task(name="recover_stale_structured_batches")
def recover_stale_structured_batches() -> int:
    """Mark orphaned batches interrupted; the next dispatch resumes pending corpus."""
    from datetime import timedelta

    cutoff = timezone.now() - timedelta(hours=2)
    stale = AnalysisBatch.objects.filter(
        prompt_version="structured_analysis_v1",
        status__in=(AnalysisBatchStatus.PENDING, AnalysisBatchStatus.RUNNING),
        updated_at__lt=cutoff,
    )
    return stale.update(
        status=AnalysisBatchStatus.FAILED,
        error_message="WORKER_INTERRUPTED: batch did not report progress for two hours",
        finished_at=timezone.now(),
    )
