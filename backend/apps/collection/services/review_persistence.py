"""NormalizedReview 到 ReviewRecord 的短事务持久化。"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from collectors.base import NormalizedReview
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.reviews.models import ReviewRecord, ReviewStatus
from apps.sources.models import SourceTarget

_WHITESPACE_PATTERN = re.compile(r"\s+")


@dataclass(frozen=True)
class PersistenceResult:
    review: ReviewRecord
    inserted: bool


def build_content_hash(source_code: str, review: NormalizedReview) -> str:
    normalized_content = _WHITESPACE_PATTERN.sub(" ", review.content).strip()
    if review.external_id:
        material = f"{source_code}{review.external_id}{normalized_content}"
    else:
        published_at = review.published_at.isoformat() if review.published_at else ""
        material = f"{source_code}{review.record_type}{published_at}{normalized_content}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def persist_review(source_target: SourceTarget, review: NormalizedReview) -> PersistenceResult:
    content_hash = build_content_hash(source_target.source.code, review)
    defaults = {
        "source_target": source_target,
        "product": source_target.product,
        "parent_external_id": review.parent_external_id or "",
        "title": review.title,
        "content": review.content,
        "published_at": review.published_at,
        "author_role": review.author_role,
        "is_official": review.is_official,
        "is_append_review": review.is_append_review,
        "software_version": review.software_version,
        "source_url": review.source_url,
        "content_hash": content_hash,
        "raw_data": review.raw_data,
        "status": ReviewStatus.NORMALIZED,
        "collected_at": timezone.now(),
    }

    try:
        with transaction.atomic():
            if review.external_id:
                instance, created = ReviewRecord.objects.get_or_create(
                    source=source_target.source,
                    external_id=review.external_id,
                    record_type=review.record_type,
                    defaults=defaults,
                )
            else:
                existing = ReviewRecord.objects.filter(
                    source=source_target.source,
                    product=source_target.product,
                    record_type=review.record_type,
                    content_hash=content_hash,
                ).first()
                if existing is not None:
                    return PersistenceResult(review=existing, inserted=False)
                instance = ReviewRecord.objects.create(
                    source=source_target.source,
                    external_id=None,
                    record_type=review.record_type,
                    **defaults,
                )
                created = True
    except IntegrityError:
        instance = ReviewRecord.objects.get(
            source=source_target.source,
            external_id=review.external_id,
            record_type=review.record_type,
        )
        created = False
    return PersistenceResult(review=instance, inserted=created)
