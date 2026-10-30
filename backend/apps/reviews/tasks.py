"""Offline Celery tasks for review governance."""

from __future__ import annotations

import logging
from typing import Any

from celery import shared_task
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.accounts.ai_service import get_user_ai_provider
from apps.reviews.models import GovernanceAIBatch, GovernanceAIReview, GovernanceTask, ReviewQuality, ReviewRecord
from apps.reviews.services.ai_governance import review_quality_with_ai
from apps.reviews.services.governance_pipeline import GovernanceProcessor, process_reviews


logger = logging.getLogger(__name__)


@shared_task(name="process_review_quality")
def process_review_quality(review_id: int) -> dict[str, Any]:
    review = ReviewRecord.objects.select_related("source", "source_target", "product").get(pk=review_id)
    decision = GovernanceProcessor().process(review, persist=True, force=True)
    return {
        "review_id": decision.review_id,
        "eligible": decision.eligible,
        "exclusion_reason": decision.exclusion_reason,
        "quality_score": decision.quality_score,
    }


@shared_task(name="process_product_reviews")
def process_product_reviews(product_id: int, batch_size: int = 100) -> dict[str, Any]:
    safe_batch_size = min(max(int(batch_size), 1), 1000)
    queryset = ReviewRecord.objects.filter(product_id=product_id)
    return process_reviews(queryset, batch_size=safe_batch_size, persist=True).as_dict()


@shared_task(bind=True, name="process_governance_batch")
def process_governance_batch(self: Any, governance_task_id: int) -> dict[str, Any]:
    """Execute the frozen batch, checkpointing progress to PostgreSQL."""
    task = GovernanceTask.objects.get(pk=governance_task_id)
    if task.status != GovernanceTask.Status.PENDING:
        return {"task_id": task.id, "status": task.status}
    task.status = GovernanceTask.Status.RUNNING
    task.started_at = timezone.now()
    task.celery_task_id = self.request.id or ""
    task.save(update_fields=("status", "started_at", "celery_task_id", "updated_at"))
    processor = GovernanceProcessor()
    failures: list[dict[str, Any]] = []
    try:
        for review_id in task.review_ids:
            try:
                review = ReviewRecord.objects.select_related("source", "source_target", "product").get(pk=review_id)
                decision = processor.process(review, persist=True, force=task.reprocess)
                task.eligible += int(decision.eligible)
                task.excluded += int(not decision.eligible)
                task.reused += int(decision.reused)
            except Exception as exc:
                failures.append({"review_id": review_id, "error_type": type(exc).__name__})
                task.failed += 1
            task.processed += 1
            task.failures = failures
            task.save(update_fields=("eligible", "excluded", "reused", "failed", "processed", "failures", "updated_at"))
            if self.request.id and not self.request.is_eager:
                self.update_state(
                    state="PROGRESS",
                    meta={"task_id": task.id, "processed": task.processed, "total": task.total},
                )
    except Exception as exc:
        task.status = GovernanceTask.Status.FAILED
        task.error_message = type(exc).__name__
        raise
    else:
        task.status = GovernanceTask.Status.PARTIAL if task.failed else GovernanceTask.Status.SUCCESS
    finally:
        task.finished_at = timezone.now()
        task.save(update_fields=("status", "error_message", "finished_at", "updated_at"))
    return {"task_id": task.id, "status": task.status, "processed": task.processed, "failed": task.failed}


@shared_task(bind=True, name="process_governance_ai_batch")
def process_governance_ai_batch(self: Any, batch_id: int, max_attempts: int = 2) -> dict[str, Any]:
    """Run a bounded AI review batch; failures are durable and individually retryable."""
    with transaction.atomic():
        batch = GovernanceAIBatch.objects.select_for_update().select_related("requested_by").get(pk=batch_id)
        if batch.status != GovernanceAIBatch.Status.PENDING:
            return {"batch_id": batch.id, "status": batch.status}
        batch.status = GovernanceAIBatch.Status.RUNNING
        batch.started_at = timezone.now()
        batch.celery_task_id = self.request.id or ""
        batch.save(update_fields=("status", "started_at", "celery_task_id", "updated_at"))
    try:
        provider = get_user_ai_provider(batch.requested_by)
        for quality_id in batch.quality_ids[batch.processed :]:
            root_id = batch.root_batch_id or batch.id
            if batch.automatic and GovernanceAIBatch.objects.filter(pk=root_id, stop_requested=True).exists():
                batch.status = GovernanceAIBatch.Status.STOPPED
                break
            try:
                result: GovernanceAIReview | None = None
                for attempt in range(min(max(max_attempts, 1), 3)):
                    result = review_quality_with_ai(quality_id, provider, force=attempt > 0)
                    batch.prompt_tokens += result.prompt_tokens or 0
                    batch.completion_tokens += result.completion_tokens or 0
                    if result.status != GovernanceAIReview.Status.ERROR:
                        break
                assert result is not None
                if result.status in (GovernanceAIReview.Status.ERROR, GovernanceAIReview.Status.FAILED):
                    batch.failed += 1
                    batch.failure_ids.append(quality_id)
                elif result.status in (
                    GovernanceAIReview.Status.UNCERTAIN,
                    GovernanceAIReview.Status.REVIEW_REQUIRED,
                ):
                    batch.uncertain += 1
                    batch.review_required += 1
                elif result.status == GovernanceAIReview.Status.ACCEPTED:
                    batch.accepted += 1
                    batch.succeeded += 1
                elif result.status == GovernanceAIReview.Status.REJECTED:
                    batch.rejected += 1
                    batch.succeeded += 1
                else:
                    batch.succeeded += 1
            except Exception:
                batch.failed += 1
                batch.failure_ids.append(quality_id)
            batch.processed += 1
            batch.save(
                update_fields=(
                    "processed",
                    "succeeded",
                    "review_required",
                    "failed",
                    "accepted",
                    "rejected",
                    "uncertain",
                    "prompt_tokens",
                    "completion_tokens",
                    "failure_ids",
                    "updated_at",
                )
            )
        if batch.status != GovernanceAIBatch.Status.STOPPED:
            batch.status = GovernanceAIBatch.Status.PARTIAL if batch.failed else GovernanceAIBatch.Status.SUCCESS
    except Exception as exc:
        batch.status = GovernanceAIBatch.Status.FAILED
        batch.error_code = str(getattr(exc, "code", type(exc).__name__))[:80]
        # Provider setup can fail before any record is processed.
        # Preserve all unprocessed ids for a later retry.
        batch.failure_ids = list(
            dict.fromkeys(
                [
                    *batch.failure_ids,
                    *batch.quality_ids[batch.processed :],
                ]
            )
        )
        batch.failed = len(batch.failure_ids)
    finally:
        batch.finished_at = timezone.now()
        batch.save(update_fields=("status", "error_code", "failed", "failure_ids", "finished_at", "updated_at"))
    if batch.automatic and batch.status in (GovernanceAIBatch.Status.SUCCESS, GovernanceAIBatch.Status.PARTIAL):
        # Each continuation is bounded to 100 rows. Failed/uncertain AI results
        # are not automatically charged again; explicit retry remains available.
        from apps.reviews.models import ReviewQuality

        with transaction.atomic():
            root = GovernanceAIBatch.objects.select_for_update().get(pk=batch.root_batch_id or batch.id)
            if root.stop_requested:
                return {"batch_id": batch.id, "status": "STOPPED", "processed": batch.processed}
            product = batch.product.__class__.objects.select_for_update().get(pk=batch.product_id)
            reviewed = GovernanceAIReview.objects.values_list("quality_id", flat=True)
            pending = ReviewQuality.objects.filter(review__product=product, eligible_for_ai=True)
            if batch.source_id is not None:
                pending = pending.filter(review__source_id=batch.source_id)
            ids = list(pending.exclude(pk__in=reviewed).order_by("pk").values_list("pk", flat=True)[:100])
            next_batch = None
            if ids:
                next_batch = GovernanceAIBatch.objects.create(
                    product=product,
                    source_id=batch.source_id,
                    requested_by=batch.requested_by,
                    automatic=True,
                    root_batch=root,
                    quality_ids=ids,
                    total=len(ids),
                )
        if next_batch is not None:
            try:
                job = process_governance_ai_batch.delay(next_batch.id)
                next_batch.celery_task_id = job.id
                next_batch.save(update_fields=("celery_task_id", "updated_at"))
            except Exception:
                next_batch.status = GovernanceAIBatch.Status.FAILED
                next_batch.error_code = "TASK_DISPATCH_FAILED"
                next_batch.save(update_fields=("status", "error_code", "updated_at"))
    return {"batch_id": batch.id, "status": batch.status, "processed": batch.processed}


@shared_task(name="recover_stale_governance_ai_batches")
def recover_stale_governance_ai_batches(stale_seconds: int = 300) -> dict[str, int]:
    """Reconcile stale AI batches after an interrupted worker lifecycle.

    Only a verified inactive Celery task may be recovered. If inspection fails,
    leave the batch untouched to avoid two workers calling the model at once.
    """
    from datetime import timedelta

    from celery import current_app

    cutoff = timezone.now() - timedelta(seconds=max(stale_seconds, 60))
    candidates = GovernanceAIBatch.objects.filter(
        status__in=[GovernanceAIBatch.Status.PENDING, GovernanceAIBatch.Status.RUNNING],
        updated_at__lt=cutoff,
    ).order_by("id")[:100]
    # A stop request is durable even when all workers are offline. Resolve
    # abandoned batches first; otherwise a restart can leave STOPPING forever.
    stopped = 0
    for candidate in candidates:
        root_id = candidate.root_batch_id or candidate.id
        if not GovernanceAIBatch.objects.filter(pk=root_id, stop_requested=True).exists():
            continue
        with transaction.atomic():
            batch = GovernanceAIBatch.objects.select_for_update().get(pk=candidate.pk)
            if batch.status not in [GovernanceAIBatch.Status.PENDING, GovernanceAIBatch.Status.RUNNING]:
                continue
            if batch.updated_at >= cutoff:
                continue
            batch.status = GovernanceAIBatch.Status.STOPPED
            batch.finished_at = timezone.now()
            batch.save(update_fields=["status", "finished_at", "updated_at"])
            stopped += 1
    try:
        inspector = current_app.control.inspect(timeout=3)
        active = inspector.active()
        reserved = inspector.reserved()
        scheduled = inspector.scheduled()
        if active is None or reserved is None or scheduled is None:
            return {"recovered": 0, "stopped": stopped, "skipped": candidates.count()}
        live_ids = set()
        for collection in (active, reserved, scheduled):
            for entries in collection.values():
                for item in entries or []:
                    task_id = item.get("id") or item.get("request", {}).get("id")
                    if task_id:
                        live_ids.add(task_id)
    except Exception:
        return {"recovered": 0, "stopped": stopped, "skipped": candidates.count()}
    recovered = 0
    for candidate in candidates:
        if candidate.celery_task_id and candidate.celery_task_id in live_ids:
            continue
        with transaction.atomic():
            batch = GovernanceAIBatch.objects.select_for_update().get(pk=candidate.pk)
            if batch.status not in [GovernanceAIBatch.Status.PENDING, GovernanceAIBatch.Status.RUNNING]:
                continue
            if batch.updated_at >= cutoff:
                continue
            root = GovernanceAIBatch.objects.get(pk=batch.root_batch_id or batch.id)
            if root.stop_requested:
                batch.status = GovernanceAIBatch.Status.STOPPED
                batch.finished_at = timezone.now()
                batch.save(update_fields=["status", "finished_at", "updated_at"])
                continue
            batch.status = GovernanceAIBatch.Status.PENDING
            batch.error_code = "RECOVERED_AFTER_WORKER_INTERRUPTION"
            batch.save(update_fields=["status", "error_code", "updated_at"])
        try:
            job = process_governance_ai_batch.delay(batch.id)
            GovernanceAIBatch.objects.filter(pk=batch.id, status="PENDING").update(celery_task_id=job.id)
            recovered += 1
        except Exception:
            GovernanceAIBatch.objects.filter(pk=batch.id, status="PENDING").update(
                status="FAILED", error_code="RECOVERY_DISPATCH_FAILED"
            )
    return {"recovered": recovered, "stopped": stopped, "skipped": 0}


@shared_task(name="run_automatic_voice_pipeline", autoretry_for=(), max_retries=0)
def run_automatic_voice_pipeline(product_id: int, source_id: int | None = None) -> dict[str, object]:
    from apps.reviews.services.automatic_pipeline import run_automatic_pipeline

    return run_automatic_pipeline(product_id, source_id).as_dict()


@shared_task(name="reconcile_automatic_voice_pipeline", time_limit=120, autoretry_for=(), max_retries=0)
def reconcile_automatic_voice_pipeline() -> dict[str, int | str]:
    if not settings.AI_AUTOMATION_ENABLED:
        return {"status": "disabled", "queued": 0}
    # Reconcile unfinished governance and AI failures with a bounded retry
    # budget. Do not requeue terminal AI decisions or exhausted failures.
    from django.db.models import Count, Q

    ungoverned = list(
        ReviewRecord.objects.filter(quality__isnull=True)
        .values_list("product_id", "source_id")
        .distinct()[:20]
    )
    terminal = (
        GovernanceAIReview.Status.ACCEPTED,
        GovernanceAIReview.Status.REJECTED,
        GovernanceAIReview.Status.UNCERTAIN,
        GovernanceAIReview.Status.SUCCEEDED,
        GovernanceAIReview.Status.REVIEW_REQUIRED,
    )
    ai_pending = (
        ReviewQuality.objects.filter(eligible_for_ai=True)
        .exclude(ai_reviews__status__in=terminal)
        .annotate(
            error_attempts=Count(
                "ai_reviews",
                filter=Q(ai_reviews__status=GovernanceAIReview.Status.ERROR),
            )
        )
        .filter(error_attempts__lt=settings.AI_AUTOMATION_MAX_ATTEMPTS)
        .values_list("review__product_id", "review__source_id")
        .distinct()[:20]
    )
    pairs = list(dict.fromkeys([*ungoverned, *list(ai_pending)]))[:20]
    queued = 0
    failed = 0
    for product_id, source_id in pairs:
        try:
            run_automatic_voice_pipeline.delay(product_id, source_id)
            queued += 1
        except Exception:
            logger.exception("automatic_pipeline_reconcile_dispatch_failed product_id=%s source_id=%s", product_id, source_id)
            failed += 1
    return {"status": "partial" if failed else "queued", "queued": queued, "dispatch_failed": failed}
