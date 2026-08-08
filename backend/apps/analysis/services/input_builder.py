"""Build traceable provider input exclusively from eligible corpus items."""

from __future__ import annotations

import hashlib

from ai.schemas.review_analysis import ReviewAnalysisInput

from apps.reviews.models import AnalysisCorpusItem, RecordType, ReviewRecord
from apps.reviews.services.context_builder import find_parent_review

PHASE5_PRODUCT = "HONOR_POWER2"
PHASE5_SOURCE = "HONOR_CLUB"


def is_phase5_target(corpus_item: AnalysisCorpusItem) -> bool:
    return corpus_item.product.normalized_name == PHASE5_PRODUCT and corpus_item.source.code == PHASE5_SOURCE


def _device_source(review: ReviewRecord | None) -> str:
    if review is None or not isinstance(review.raw_data, dict):
        return ""
    value = review.raw_data.get("device_source")
    return str(value) if isinstance(value, str) else ""


def _thread_and_parent(review: ReviewRecord) -> tuple[ReviewRecord | None, ReviewRecord | None]:
    if review.record_type == RecordType.THREAD:
        return review, None
    parent = find_parent_review(review)
    thread = parent
    for _ in range(3):
        if thread is None or thread.record_type == RecordType.THREAD:
            break
        thread = find_parent_review(thread)
    return thread, parent


def build_review_analysis_input(corpus_item: AnalysisCorpusItem) -> ReviewAnalysisInput:
    if not corpus_item.eligible or not corpus_item.quality.eligible_for_ai:
        raise ValueError("CORPUS_ITEM_NOT_ELIGIBLE")
    if not is_phase5_target(corpus_item):
        raise ValueError("PHASE5_TARGET_ONLY")
    review = corpus_item.review
    thread, parent = _thread_and_parent(review)
    return ReviewAnalysisInput(
        review_id=str(review.id),
        product_model=corpus_item.product.name,
        source=corpus_item.source.code,
        record_type=review.record_type,
        author_role=review.author_role,
        is_official=review.is_official,
        title=review.title or None,
        content=review.content,
        rating=float(review.rating) if review.rating is not None else None,
        software_version=review.software_version or None,
        published_at=review.published_at.isoformat() if review.published_at else None,
        device_source=_device_source(review) or _device_source(parent) or _device_source(thread),
        thread_review_id=str(thread.id) if thread else "",
        thread_title=thread.title if thread else "",
        thread_content=thread.content if thread else "",
        parent_review_id=str(parent.id) if parent else "",
        parent_content=parent.content if parent else "",
        context_text=corpus_item.context_text,
    )


def compute_input_hash(corpus_item: AnalysisCorpusItem, *, prompt_version: str) -> str:
    material = "\x1f".join(
        (
            corpus_item.corpus_version,
            corpus_item.normalized_text,
            corpus_item.context_text,
            prompt_version,
        )
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()
