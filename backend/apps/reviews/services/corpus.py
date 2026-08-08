"""Stable query entry point reserved for Phase 5."""

from __future__ import annotations

from django.db.models import QuerySet

from apps.reviews.models import AnalysisCorpusItem


def get_analysis_corpus(product_id: int, *, corpus_version: str) -> QuerySet[AnalysisCorpusItem]:
    return AnalysisCorpusItem.objects.filter(
        product_id=product_id,
        corpus_version=corpus_version,
        eligible=True,
    ).select_related("review", "quality", "product", "source")
