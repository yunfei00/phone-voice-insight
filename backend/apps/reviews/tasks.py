"""Offline Celery tasks for review governance."""

from __future__ import annotations

from typing import Any

from celery import shared_task

from django.utils import timezone
from apps.reviews.models import GovernanceTask, ReviewRecord
from apps.reviews.services.governance_pipeline import GovernanceProcessor, process_reviews


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
def process_governance_batch(self, governance_task_id: int) -> dict[str, Any]:
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
            self.update_state(state="PROGRESS", meta={"task_id": task.id, "processed": task.processed, "total": task.total})
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
