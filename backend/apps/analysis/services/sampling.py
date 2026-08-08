"""Deterministic, coverage-oriented corpus selection."""

from __future__ import annotations

import hashlib
from collections.abc import Callable

from django.db.models import QuerySet

from apps.reviews.models import AnalysisCorpusItem, RecordType

DEFAULT_SAMPLE_SEED = 20260808


def _rank(item: AnalysisCorpusItem, seed: int) -> str:
    return hashlib.sha256(f"{seed}:{item.review_id}".encode()).hexdigest()


def select_corpus_items(
    queryset: QuerySet[AnalysisCorpusItem],
    *,
    limit: int | None,
    record_id: int | None = None,
    seed: int = DEFAULT_SAMPLE_SEED,
) -> list[AnalysisCorpusItem]:
    queryset = queryset.select_related("review", "quality", "product", "source")
    if record_id is not None:
        item = queryset.filter(review_id=record_id).first()
        return [item] if item is not None else []
    items = list(queryset)
    ranked = sorted(items, key=lambda item: _rank(item, seed))
    if limit is None or limit >= len(ranked):
        return ranked

    selected: list[AnalysisCorpusItem] = []
    selected_ids: set[int] = set()

    def pick(predicate: Callable[[AnalysisCorpusItem], bool]) -> None:
        candidate = next((item for item in ranked if item.review_id not in selected_ids and predicate(item)), None)
        if candidate is not None and len(selected) < limit:
            selected.append(candidate)
            selected_ids.add(candidate.review_id)

    keywords = {
        "positive": ("好", "强", "流畅", "不错"),
        "negative": ("差", "掉电", "耗电", "热", "烫", "卡", "断", "问题"),
        "battery": ("续航", "掉电", "耗电", "电池"),
        "heating": ("发热", "热", "烫"),
    }
    pick(lambda item: item.record_type == RecordType.THREAD)
    pick(lambda item: item.record_type == RecordType.REPLY)
    pick(lambda item: len(item.normalized_text) <= 12)
    pick(lambda item: len(item.normalized_text) >= 120)
    pick(lambda item: item.record_type == RecordType.REPLY and bool(item.context_text))
    pick(lambda item: any(word in item.normalized_text for word in keywords["positive"]))
    pick(lambda item: any(word in item.normalized_text for word in keywords["negative"]))
    pick(
        lambda item: (
            any(word in item.normalized_text for word in keywords["battery"])
            and any(word in item.normalized_text for word in keywords["heating"])
        )
    )
    for item in ranked:
        if len(selected) >= limit:
            break
        if item.review_id not in selected_ids:
            selected.append(item)
            selected_ids.add(item.review_id)
    return selected
