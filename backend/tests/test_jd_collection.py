from datetime import UTC, datetime

import pytest
from collectors.base import (
    BaseCollector,
    CollectionRequest,
    CollectorTarget,
    NormalizedReview,
    RawPage,
    RawRecord,
    ValidationResult,
)

from apps.collection.models import CollectionStatus, CollectionTask
from apps.collection.services.collection_runner import run_collection
from apps.products.models import Product, ProductVariant
from apps.reviews.models import ReviewRecord
from apps.sources.models import DataSource, SourceProductVariant, SourceTarget, SourceType, TargetType


class FixtureJDCollector(BaseCollector):
    def validate_target(self, target: CollectorTarget) -> ValidationResult:
        del target
        return ValidationResult(is_valid=True)

    def fetch_page(self, request: CollectionRequest) -> RawPage:
        return RawPage(
            content="fixture",
            fetched_at=datetime.now(UTC),
            checkpoint=request.checkpoint,
            metadata={**request.checkpoint.metadata, "http_status": 200, "elapsed_ms": 1},
        )

    def parse_records(self, raw_page: RawPage) -> list[RawRecord]:
        if raw_page.metadata["page_kind"] == "product":
            return [RawRecord(external_id="jd_product:100310496358", record_type="PRODUCT_METADATA", payload={})]
        return [
            RawRecord(
                external_id="jd_review:900000001",
                record_type="REVIEW",
                payload={"comment_id": "900000001"},
            ),
            RawRecord(
                external_id="jd_append:910000001",
                record_type="APPEND_REVIEW",
                payload={"comment_id": "900000001"},
            ),
        ]

    def normalize_record(self, raw_record: RawRecord) -> NormalizedReview:
        is_append = raw_record.record_type == "APPEND_REVIEW"
        return NormalizedReview(
            external_id=raw_record.external_id,
            parent_external_id="jd_review:900000001" if is_append else None,
            record_type=raw_record.record_type,
            content="追评内容" if is_append else "主评价内容",
            rating=None if is_append else 5,
            published_at=datetime(2026, 8, 1, 10, 20, tzinfo=UTC),
            author_role="USER",
            is_append_review=is_append,
            variant_external_id="100310496358",
            variant_attributes={"memory": "12GB", "storage": "512GB", "color": "旭日橙"},
            raw_data={"jd_comment_id": "900000001", "jd_sku_id": "100310496358"},
        )


@pytest.fixture
def jd_source_target(product: Product) -> SourceTarget:
    source, _ = DataSource.objects.update_or_create(
        code="JD", defaults={"name": "京东", "source_type": SourceType.ECOMMERCE}
    )
    target, _ = SourceTarget.objects.update_or_create(
        source=source,
        name="荣耀Power2京东测试入口",
        defaults={
            "product": product,
            "target_type": TargetType.PRODUCT,
            "target_url": "https://item.jd.com/100310496358.html",
            "external_id": "jd:100310496358",
            "config_json": {
                "product_id": "100310496358",
                "request_interval_seconds": 4,
                "max_pages": 1,
                "page_size": 10,
            },
            "is_active": True,
        },
    )
    variant = ProductVariant.objects.create(
        product=product,
        memory="12GB",
        storage="512GB",
        color="旭日橙",
        sku_name="12GB+512GB 旭日橙",
    )
    SourceProductVariant.objects.create(
        source=source,
        product=product,
        product_variant=variant,
        external_id="100310496358",
        source_target=target,
        attributes_json={"memory": "12GB", "storage": "512GB", "color": "旭日橙"},
    )
    return target


@pytest.mark.django_db
def test_jd_runner_persists_rating_variant_checkpoint_and_deduplicates(
    jd_source_target: SourceTarget,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "apps.collection.services.collection_runner.get_collector",
        lambda _source_code: FixtureJDCollector(),
    )
    task = CollectionTask.objects.create(source_target=jd_source_target, requested_limit=10)

    first = run_collection(task.id, pages_override=1)
    task.refresh_from_db()
    assert first.scanned_threads == 1
    assert first.inserted_records == 2
    assert task.status == CollectionStatus.SUCCESS
    assert task.last_checkpoint == {
        "page": 1,
        "page_size": 10,
        "last_comment_id": "900000001",
        "sort_mode": "CURRENT_PAGE_DEFAULT",
    }
    review = ReviewRecord.objects.get(record_type="REVIEW")
    assert review.rating == 5
    assert review.product_variant is not None
    assert review.product_variant.sku_name == "12GB+512GB 旭日橙"

    task.transition_to(CollectionStatus.PENDING)
    task.last_checkpoint = {}
    task.save(update_fields=("status", "last_checkpoint", "updated_at"))
    second = run_collection(task.id, pages_override=1)
    task.refresh_from_db()
    assert second.inserted_records == 0
    assert second.skipped_records == 2
    assert ReviewRecord.objects.filter(source=jd_source_target.source).count() == 2
