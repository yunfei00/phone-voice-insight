"""Second-pass product relevance checks for governance."""

from __future__ import annotations

import re

from apps.products.models import ProductAlias
from apps.reviews.models import RecordType, ReviewRecord
from apps.reviews.services.context_builder import find_parent_review
from apps.reviews.services.text_normalizer import normalize_text

_SEPARATORS = re.compile(r"[\s\-_]+")
_HONOR_MODEL = re.compile(r"荣耀\s*[a-z]+\s*\d+[a-z0-9]*", re.IGNORECASE)


def _compact(value: str) -> str:
    return _SEPARATORS.sub("", normalize_text(value).casefold())


def _record_search_text(review: ReviewRecord) -> str:
    raw_values: list[str] = []
    if isinstance(review.raw_data, dict):
        for key in ("device_source", "thread_title"):
            value = review.raw_data.get(key)
            if isinstance(value, str):
                raw_values.append(value)
        tags = review.raw_data.get("topic_tags")
        if isinstance(tags, list):
            raw_values.extend(str(value) for value in tags)
    return _compact(" ".join((review.title, review.content, *raw_values)))


def _primary_search_text(review: ReviewRecord) -> str:
    return _compact(" ".join((review.title, review.content)))


def _aliases(review: ReviewRecord) -> tuple[str, ...]:
    values = list(ProductAlias.objects.filter(product_id=review.product_id).values_list("alias", flat=True))
    values.append(review.product.name)
    values.append(review.product.normalized_name)
    return tuple(value for alias in values if (value := _compact(alias)))


def is_product_related(review: ReviewRecord, *, parent: ReviewRecord | None = None) -> bool:
    aliases = _aliases(review)
    primary_text = _primary_search_text(review)
    explicit_honor_models = _HONOR_MODEL.findall(normalize_text(f"{review.title}\n{review.content}"))
    if explicit_honor_models and not any(alias in primary_text for alias in aliases):
        return False
    if any(alias in _record_search_text(review) for alias in aliases):
        return True
    if review.record_type in {RecordType.REPLY, RecordType.OFFICIAL_REPLY}:
        parent = parent or find_parent_review(review)
        if parent is not None and parent.product_id == review.product_id:
            return any(alias in _record_search_text(parent) for alias in aliases)
    return False
