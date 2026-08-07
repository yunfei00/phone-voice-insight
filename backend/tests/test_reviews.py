import hashlib

import pytest
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.test import APIClient

from apps.products.models import Product, ProductVariant
from apps.reviews.models import RecordType, ReviewRecord
from apps.sources.models import DataSource, SourceTarget


def make_review(
    *,
    source: DataSource,
    source_target: SourceTarget,
    product: Product,
    external_id: str,
    content: str,
    record_type: str = RecordType.REVIEW,
    rating: float | None = None,
    product_variant: ProductVariant | None = None,
) -> ReviewRecord:
    return ReviewRecord.objects.create(
        source=source,
        source_target=source_target,
        product=product,
        external_id=external_id,
        record_type=record_type,
        content=content,
        rating=rating,
        product_variant=product_variant,
        content_hash=hashlib.sha256(content.encode()).hexdigest(),
        raw_data={"content": content},
        collected_at=timezone.now(),
    )


@pytest.mark.django_db
def test_review_external_id_uniqueness(
    source: DataSource,
    source_target: SourceTarget,
    product: Product,
) -> None:
    make_review(
        source=source,
        source_target=source_target,
        product=product,
        external_id="review-1",
        content="第一条",
    )

    with pytest.raises(IntegrityError), transaction.atomic():
        make_review(
            source=source,
            source_target=source_target,
            product=product,
            external_id="review-1",
            content="重复记录",
        )


@pytest.mark.django_db
def test_review_filter_api(
    api_client: APIClient,
    source: DataSource,
    source_target: SourceTarget,
    product: Product,
) -> None:
    make_review(
        source=source,
        source_target=source_target,
        product=product,
        external_id="review-1",
        content="用户评价",
    )
    make_review(
        source=source,
        source_target=source_target,
        product=product,
        external_id="reply-1",
        content="官方回复",
        record_type=RecordType.OFFICIAL_REPLY,
    )

    response = api_client.get("/api/v1/reviews/", {"record_type": RecordType.REVIEW, "search": "用户"})

    assert response.status_code == 200
    assert response.json()["count"] == 1
    assert response.json()["results"][0]["external_id"] == "review-1"


@pytest.mark.django_db
def test_review_filter_api_supports_source_code_rating_and_variant(
    api_client: APIClient,
    source: DataSource,
    source_target: SourceTarget,
    product: Product,
) -> None:
    variant = ProductVariant.objects.create(
        product=product,
        memory="12GB",
        storage="512GB",
        color="旭日橙",
        sku_name="12GB+512GB 旭日橙",
    )
    make_review(
        source=source,
        source_target=source_target,
        product=product,
        external_id="jd_review:filtered",
        content="用于组合筛选",
        rating=5,
        product_variant=variant,
    )

    response = api_client.get(
        "/api/v1/reviews/",
        {"source": "JD", "record_type": "REVIEW", "rating": "5", "product_variant": str(variant.id)},
    )

    assert response.status_code == 200
    assert response.json()["count"] == 1
    row = response.json()["results"][0]
    assert row["variant_name"] == "12GB+512GB 旭日橙"
    assert row["rating"] == "5.0"
