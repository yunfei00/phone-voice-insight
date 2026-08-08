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
