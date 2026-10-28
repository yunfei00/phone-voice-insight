"""NormalizedReview 到 ReviewRecord 的短事务持久化。"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from collectors.base import NormalizedReview
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.products.models import ProductVariant
from apps.reviews.models import ReviewRecord, ReviewStatus
from apps.sources.models import SourceProductVariant, SourceTarget

_WHITESPACE_PATTERN = re.compile(r"\s+")


@dataclass(frozen=True)
class PersistenceResult:
    review: ReviewRecord
    inserted: bool
    updated: bool = False


def resolve_product_variant(source_target: SourceTarget, review: NormalizedReview) -> ProductVariant | None:
    if review.variant_external_id:
        mapping = (
            SourceProductVariant.objects.select_related("product_variant")
            .filter(
                source=source_target.source,
                product=source_target.product,
                external_id=review.variant_external_id,
                is_active=True,
            )
            .first()
        )
        if mapping is not None:
            return mapping.product_variant

    attributes = {key.casefold(): value.strip().casefold() for key, value in review.variant_attributes.items()}
    required = {"memory", "storage", "color"}
    if not required.issubset(attributes) or not all(attributes[key] for key in required):
        return None
    matches = source_target.product.variants.filter(
        memory__iexact=attributes["memory"],
        storage__iexact=attributes["storage"],
        color__iexact=attributes["color"],
        is_active=True,
    )
    return matches.first() if matches.count() == 1 else None


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
    product_variant = resolve_product_variant(source_target, review)
    ip_location = str(review.raw_data.get("ip_location") or review.raw_data.get("public_region") or "")
    profile_region = str(review.raw_data.get("profile_region") or "")
    source_region = ip_location or profile_region
    region_evidence = "public_ip_region" if ip_location else "public_profile_region" if profile_region else ""
    defaults = {
        "source_target": source_target,
        "product": source_target.product,
        "product_variant": product_variant,
        "parent_external_id": review.parent_external_id or "",
        "title": review.title,
        "content": review.content,
        "rating": review.rating,
        "published_at": review.published_at,
        "source_region": source_region,
        "region_evidence": region_evidence,
        "author_role": review.author_role,
        "is_official": review.is_official,
        "is_append_review": review.is_append_review,
        "software_version": review.software_version,
        "source_url": review.source_url or source_target.target_url,
        "content_hash": content_hash,
        "raw_data": review.raw_data,
        "status": ReviewStatus.NORMALIZED,
        "collected_at": timezone.now(),
    }

    try:
        with transaction.atomic():
            if review.external_id:
                instance = (
                    ReviewRecord.objects.select_for_update()
                    .filter(
                        source=source_target.source,
                        external_id=review.external_id,
                        record_type=review.record_type,
                    )
                    .first()
                )
                if instance is None:
                    instance = ReviewRecord.objects.create(
                        source=source_target.source,
                        external_id=review.external_id,
                        record_type=review.record_type,
                        **defaults,
                    )
                    created = True
                    updated = False
                else:
                    created = False
                    merged_raw_data = {**instance.raw_data, **review.raw_data}
                    mutable = {
                        "source_target": source_target,
                        "product": source_target.product,
                        "source_url": review.source_url or instance.source_url or source_target.target_url,
                        "raw_data": merged_raw_data,
                        "collected_at": defaults["collected_at"],
                    }
                    if review.record_type == "THREAD" and review.title:
                        mutable["title"] = review.title
                    if not instance.source_region and defaults["source_region"]:
                        mutable["source_region"] = defaults["source_region"]
                        mutable["region_evidence"] = defaults["region_evidence"]
                    if instance.published_at is None and review.published_at is not None:
                        mutable["published_at"] = review.published_at
                    if not instance.content.strip() and review.content.strip():
                        mutable["content"] = review.content
                        mutable["content_hash"] = content_hash
                    updated = any(getattr(instance, name) != value for name, value in mutable.items())
                    if updated:
                        for name, value in mutable.items():
                            setattr(instance, name, value)
                        instance.save(update_fields=(*mutable.keys(), "updated_at"))
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
                updated = False
    except IntegrityError:
        instance = ReviewRecord.objects.get(
            source=source_target.source,
            external_id=review.external_id,
            record_type=review.record_type,
        )
        created = False
        updated = False
    return PersistenceResult(review=instance, inserted=created, updated=updated)
