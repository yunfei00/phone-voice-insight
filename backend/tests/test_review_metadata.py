from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from collectors.base import NormalizedReview
from django.core.management import call_command
from django.utils import timezone
from rest_framework.test import APIClient

from apps.collection.services.review_persistence import persist_review
from apps.products.models import Product
from apps.reviews.models import ReviewRecord
from apps.sources.models import SourceTarget


def make_review(
    source_target: SourceTarget,
    *,
    external_id: str,
    record_type: str = "REPLY",
    published_at: datetime | None = None,
    source_region: str = "",
    region_evidence: str = "",
    raw_data: dict[str, object] | None = None,
) -> ReviewRecord:
    return ReviewRecord.objects.create(
        source=source_target.source,
        source_target=source_target,
        product=source_target.product,
        external_id=external_id,
        record_type=record_type,
        content="测试内容",
        published_at=published_at,
        source_region=source_region,
        region_evidence=region_evidence,
        content_hash=external_id.ljust(64, "0")[:64],
        raw_data=raw_data or {},
        collected_at=datetime(2026, 10, 28, 16, 30, tzinfo=ZoneInfo("Asia/Shanghai")),
    )


@pytest.mark.django_db
def test_metadata_completeness_api_distinguishes_ip_and_profile_regions(
    api_client: APIClient,
    source_target: SourceTarget,
) -> None:
    make_review(
        source_target,
        external_id="with-ip",
        published_at=timezone.now(),
        source_region="陕西",
        region_evidence="public_ip_region",
        raw_data={"ip_location": "陕西"},
    )
    make_review(
        source_target,
        external_id="missing",
        raw_data={
            "published_at_parse_reason": "source_time_missing",
            "ip_location_parse_reason": "source_ip_location_unknown",
            "profile_region_parse_reason": "profile_region_not_publicly_labeled",
        },
    )

    response = api_client.get("/api/v1/reviews/metadata-completeness/")

    assert response.status_code == 200
    body = response.json()
    assert body["summary"] == {
        "total": 2,
        "published_at_count": 1,
        "published_at_rate": 0.5,
        "ip_location_count": 1,
        "ip_location_rate": 0.5,
        "profile_region_count": 0,
        "profile_region_rate": 0.0,
    }
    assert body["failure_reasons"]["published_at"] == {"source_time_missing": 1}
    assert body["failure_reasons"]["ip_location"] == {"source_ip_location_unknown": 1}
    assert body["failure_reasons"]["profile_region"] == {"profile_region_not_publicly_labeled": 2}


@pytest.mark.django_db
def test_review_api_exposes_ip_location_without_claiming_profile_region(
    api_client: APIClient,
    source_target: SourceTarget,
) -> None:
    review = make_review(
        source_target,
        external_id="region-fields",
        source_region="广西",
        region_evidence="public_ip_region",
    )

    response = api_client.get(f"/api/v1/reviews/{review.id}/")

    assert response.status_code == 200
    assert response.json()["ip_location"] == "广西"
    assert response.json()["profile_region"] == ""


@pytest.mark.django_db
def test_backfill_uses_collection_time_for_legacy_yesterday_value(
    source_target: SourceTarget,
    product: Product,
) -> None:
    del product
    review = make_review(
        source_target,
        external_id="legacy-yesterday",
        raw_data={"published_at_raw": "昨天 11:04"},
    )

    call_command("backfill_review_metadata", apply=True, source_target=source_target.id)

    review.refresh_from_db()
    assert review.published_at == datetime(2026, 10, 27, 11, 4, tzinfo=ZoneInfo("Asia/Shanghai"))
    assert review.raw_data["published_at_raw"] == "昨天 11:04"
    assert review.raw_data["published_at_normalized"] == "2026-10-27T11:04:00+08:00"
    assert review.raw_data["published_at_timezone"] == "Asia/Shanghai"
    assert review.raw_data["ip_location_parse_reason"] == "legacy_ip_location_not_captured"


@pytest.mark.django_db
def test_persistence_uses_explicit_ip_location_evidence(source_target: SourceTarget) -> None:
    result = persist_review(
        source_target,
        NormalizedReview(
            external_id="honor-region",
            parent_external_id=None,
            record_type="THREAD",
            content="公开页面内容",
            raw_data={
                "ip_location": "广东",
                "region_evidence": "public_ip_region",
                "profile_region_parse_reason": "profile_region_not_publicly_labeled",
            },
        ),
    )

    assert result.review.source_region == "广东"
    assert result.review.region_evidence == "public_ip_region"


@pytest.mark.django_db
def test_thread_view_keeps_metadata_on_the_same_thread_record(
    api_client: APIClient,
    source_target: SourceTarget,
) -> None:
    thread = make_review(
        source_target,
        external_id="thread:metadata",
        record_type="THREAD",
        published_at=timezone.now(),
        source_region="北京",
        region_evidence="public_ip_region",
        raw_data={"thread_id": "metadata", "ip_location": "北京"},
    )

    response = api_client.get("/api/v1/thread-trees/")

    assert response.status_code == 200
    item = next(row for row in response.json()["results"] if row["id"] == thread.id)
    assert item["ip_location"] == "北京"
    assert item["profile_region"] == ""
