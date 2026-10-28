"""Selection policy shared by preview, synchronous and background governance."""
from apps.reviews.models import GovernanceTask, ReviewRecord


def governance_candidates(*, product_id: int, source_id: int | None = None, reprocess: bool = False):
    queryset = ReviewRecord.objects.filter(product_id=product_id)
    if source_id is not None:
        queryset = queryset.filter(source_id=source_id)
    if not reprocess:
        # Only missing quality records are considered new. Existing exclusions still count as processed.
        queryset = queryset.filter(quality__isnull=True)
    # A queued or running task owns its frozen IDs until it finishes.
    active = GovernanceTask.objects.filter(
        status__in=[GovernanceTask.Status.PENDING, GovernanceTask.Status.RUNNING]
    ).filter(product_id=product_id)
    reserved = set()
    for ids in active.values_list("review_ids", flat=True):
        reserved.update(ids)
    if reserved:
        queryset = queryset.exclude(id__in=reserved)
    return queryset.order_by("id")


def governance_selection(*, product_id: int, source_id: int | None = None, limit: int = 20, reprocess: bool = False):
    candidates = governance_candidates(product_id=product_id, source_id=source_id, reprocess=reprocess)
    return list(candidates.values_list("id", flat=True)[:limit])
