"""发布时间与公开地域字段完整率统计。"""

from __future__ import annotations

import re
from collections import Counter
from typing import Any

from django.db.models import Count, Q, QuerySet

from apps.reviews.models import ReviewRecord


def _rate(value: int, total: int) -> float:
    return round(value / total, 4) if total else 0.0


def _counts(queryset: QuerySet[ReviewRecord]) -> dict[str, int | float]:
    values = queryset.aggregate(
        total=Count("id"),
        published_at=Count("id", filter=Q(published_at__isnull=False)),
        ip_location=Count(
            "id",
            filter=Q(region_evidence="public_ip_region") & ~Q(source_region=""),
        ),
        profile_region=Count(
            "id",
            filter=Q(region_evidence="public_profile_region") & ~Q(source_region=""),
        ),
    )
    total = int(values["total"] or 0)
    published = int(values["published_at"] or 0)
    ip_location = int(values["ip_location"] or 0)
    profile_region = int(values["profile_region"] or 0)
    return {
        "total": total,
        "published_at_count": published,
        "published_at_rate": _rate(published, total),
        "ip_location_count": ip_location,
        "ip_location_rate": _rate(ip_location, total),
        "profile_region_count": profile_region,
        "profile_region_rate": _rate(profile_region, total),
    }


def _published_failure_reasons(queryset: QuerySet[ReviewRecord]) -> dict[str, int]:
    grouped = (
        queryset.filter(published_at__isnull=True)
        .values("raw_data__published_at_parse_reason", "raw_data__published_at_raw")
        .annotate(count=Count("id"))
    )
    reasons: Counter[str] = Counter()
    for row in grouped:
        reason = str(row["raw_data__published_at_parse_reason"] or "")
        raw_value = str(row["raw_data__published_at_raw"] or "")
        if not reason:
            if raw_value.startswith(("今天", "昨天", "前天")):
                reason = "legacy_relative_time_not_normalized"
            elif re.search(r"\d+\s*天前", raw_value):
                reason = "relative_day_without_time_precision"
            elif raw_value:
                reason = "legacy_time_parse_failed"
            else:
                reason = "source_time_missing_or_legacy_not_captured"
        reasons[reason] += int(row["count"])
    return dict(sorted(reasons.items()))


def _region_failure_reasons(
    queryset: QuerySet[ReviewRecord],
    *,
    evidence: str,
    raw_reason_key: str,
    legacy_reason: str,
) -> dict[str, int]:
    grouped = (
        queryset.exclude(region_evidence=evidence).values(f"raw_data__{raw_reason_key}").annotate(count=Count("id"))
    )
    reasons: Counter[str] = Counter()
    for row in grouped:
        reason = str(row[f"raw_data__{raw_reason_key}"] or legacy_reason)
        reasons[reason] += int(row["count"])
    return dict(sorted(reasons.items()))


def metadata_completeness(queryset: QuerySet[ReviewRecord]) -> dict[str, Any]:
    """Return aggregate completeness without loading review rows into memory."""

    by_product = []
    product_ids = queryset.order_by().values_list("product_id", flat=True).distinct()
    for product_id in product_ids:
        product_queryset = queryset.filter(product_id=product_id)
        product = product_queryset.values("product_id", "product__name").first()
        if product is not None:
            by_product.append(
                {
                    "product": product["product_id"],
                    "product_name": product["product__name"],
                    **_counts(product_queryset),
                }
            )

    by_record_type = []
    record_types = queryset.order_by().values_list("record_type", flat=True).distinct()
    for record_type in record_types:
        by_record_type.append({"record_type": record_type, **_counts(queryset.filter(record_type=record_type))})

    return {
        "summary": _counts(queryset),
        "by_product": sorted(by_product, key=lambda item: str(item["product_name"])),
        "by_record_type": sorted(by_record_type, key=lambda item: str(item["record_type"])),
        "failure_reasons": {
            "published_at": _published_failure_reasons(queryset),
            "ip_location": _region_failure_reasons(
                queryset,
                evidence="public_ip_region",
                raw_reason_key="ip_location_parse_reason",
                legacy_reason="legacy_ip_location_not_captured",
            ),
            "profile_region": _region_failure_reasons(
                queryset,
                evidence="public_profile_region",
                raw_reason_key="profile_region_parse_reason",
                legacy_reason="profile_region_not_publicly_labeled",
            ),
        },
    }
