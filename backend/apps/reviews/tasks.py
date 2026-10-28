"""Offline Celery tasks for review governance."""

from __future__ import annotations

from typing import Any

from celery import shared_task

from apps.reviews.models import ReviewRecord
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
def process_governance_batch(self, review_ids: list[int], reprocess: bool = False) -> dict[str, Any]:
    """Process a frozen, bounded set of review IDs and report incremental progress."""
    if len(review_ids) > 1000:
        raise ValueError("A governance task cannot exceed 1000 records")
    processor = GovernanceProcessor()
    eligible = excluded = reused = 0
    failures: list[dict[str, Any]] = []
    total = len(review_ids)
    for index, review_id in enumerate(review_ids, 1):
        try:
            review = ReviewRecord.objects.select_related("source", "source_target", "product").get(pk=review_id)
            decision = processor.process(review, persist=True, force=reprocess)
            eligible += int(decision.eligible)
            excluded += int(not decision.eligible)
            reused += int(decision.reused)
        except Exception as exc:
            # Do not leak exception details or raw user content to API clients.
            failures.append({"review_id": review_id, "error_type": type(exc).__name__})
        self.update_state(state="PROGRESS", meta={
            "total": total, "processed": index, "eligible": eligible,
            "excluded": excluded, "reused": reused, "failed": len(failures),
        })
    return {
        "total": total, "processed": total, "eligible": eligible,
        "excluded": excluded, "reused": reused, "failed": len(failures),
        "failures": failures,
    }
