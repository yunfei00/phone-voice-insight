"""Build Phase 5 v3 by preserving every still-valid v2 sample."""

from __future__ import annotations

from collections.abc import Callable

from django.db.models import QuerySet

from apps.analysis.services.evaluation_samples import load_evaluation_sample
from apps.analysis.services.sampling import (
    aspect_candidate_count,
    is_context_candidate,
    sample_coverage,
    select_corpus_items,
)
from apps.reviews.models import AnalysisCorpusItem, ContentPurpose, RecordType

PHASE5_V3_SEED = 20260808


def select_phase5_poc_v3(queryset: QuerySet[AnalysisCorpusItem]) -> tuple[list[AnalysisCorpusItem], list[int]]:
    eligible = queryset.filter(
        eligible=True,
        quality__eligible_for_ai=True,
        quality__has_product_experience_signal=True,
    ).select_related("review", "quality", "product", "source")
    v2 = load_evaluation_sample("phase5-poc-v2")
    item_map = {item.review_id: item for item in eligible.filter(review_id__in=v2.review_ids)}
    selected = [item_map[review_id] for review_id in v2.review_ids if review_id in item_map]
    excluded_ids = [review_id for review_id in v2.review_ids if review_id not in item_map]
    selected_ids = {item.review_id for item in selected}
    ranked = [
        item
        for item in select_corpus_items(eligible.exclude(review_id__in=selected_ids), limit=None, seed=PHASE5_V3_SEED)
        if item.review_id not in selected_ids
    ]

    def choose(predicate: Callable[[AnalysisCorpusItem], bool]) -> None:
        nonlocal ranked
        if len(selected) >= 20:
            return
        candidate = next((item for item in ranked if predicate(item)), None)
        if candidate is not None:
            selected.append(candidate)
            selected_ids.add(candidate.review_id)
            ranked = [item for item in ranked if item.review_id != candidate.review_id]

    while len(selected) < 20 and sum(is_context_candidate(item) for item in selected) < 3:
        before = len(selected)
        choose(is_context_candidate)
        if len(selected) == before:
            break
    while len(selected) < 20 and sum(aspect_candidate_count(item) >= 2 for item in selected) < 5:
        before = len(selected)
        choose(lambda item: aspect_candidate_count(item) >= 2)
        if len(selected) == before:
            break
    if len(selected) < 20 and not any(item.quality.content_purpose == ContentPurpose.QUESTION for item in selected):
        choose(lambda item: item.quality.content_purpose == ContentPurpose.QUESTION)
    for item in ranked:
        if len(selected) >= 20:
            break
        selected.append(item)

    coverage = sample_coverage(selected)
    if len(selected) != 20:
        raise ValueError("PHASE5_POC_V3_REQUIRES_TWENTY_ITEMS")
    if coverage["thread"] < 5 or coverage["reply"] < 10:
        raise ValueError("PHASE5_POC_V3_RECORD_TYPE_COVERAGE_FAILED")
    if coverage["context_dependent_candidates"] < 3:
        raise ValueError("PHASE5_POC_V3_CONTEXT_COVERAGE_FAILED")
    if coverage["multi_aspect_candidates"] < 5:
        raise ValueError("PHASE5_POC_V3_MULTI_ASPECT_COVERAGE_FAILED")
    if not any(item.quality.content_purpose == ContentPurpose.QUESTION for item in selected):
        raise ValueError("PHASE5_POC_V3_QUESTION_COVERAGE_FAILED")
    if any(item.record_type not in {RecordType.THREAD, RecordType.REPLY} for item in selected):
        raise ValueError("PHASE5_POC_V3_UNSUPPORTED_RECORD_TYPE")
    return selected, excluded_ids
