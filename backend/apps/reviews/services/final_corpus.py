"""Canonical, deduplicated AI-governed corpus selection."""

from django.db.models import OuterRef, QuerySet, Subquery

from apps.reviews.models import GovernanceAIReview, ReviewQuality, ReviewRecord


def final_corpus_reviews() -> QuerySet[ReviewRecord]:
    """Only records whose latest governance decision accepts eligible content.

    A later rejection, uncertainty or error invalidates an earlier acceptance.
    """
    latest = (
        GovernanceAIReview.objects.filter(quality_id=OuterRef("pk")).order_by("-created_at", "-pk").values("status")[:1]
    )
    quality_ids = (
        ReviewQuality.objects.filter(eligible_for_ai=True, is_official_content=False)
        .annotate(latest_governance_status=Subquery(latest))
        .filter(latest_governance_status=GovernanceAIReview.Status.ACCEPTED)
        .values("review_id")
    )
    return ReviewRecord.objects.filter(pk__in=quality_ids)
