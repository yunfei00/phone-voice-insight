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
from apps.products.models import Product
from apps.reviews.models import ReviewRecord
from apps.sources.models import DataSource, SourceTarget, SourceType, TargetType


class FixtureHonorCollector(BaseCollector):
    def validate_target(self, target: CollectorTarget) -> ValidationResult:
        del target
        return ValidationResult(is_valid=True)

    def fetch_page(self, request: CollectionRequest) -> RawPage:
        return RawPage(
            content="fixture",
            fetched_at=datetime.now(UTC),
            checkpoint=request.checkpoint,
            metadata={
                **request.checkpoint.metadata,
                "request_url": request.target.target_url,
                "http_status": 200,
                "elapsed_ms": 1,
            },
        )

    def parse_records(self, raw_page: RawPage) -> list[RawRecord]:
        if raw_page.metadata["page_kind"] == "topic":
            return [
                RawRecord(
                    external_id="thread_link:10001",
                    record_type="THREAD_LINK",
                    payload={
                        "thread_id": "10001",
                        "thread_url": "https://club.honor.com/cn/thread-10001-1-1.html",
                        "title": "荣耀Power2 真实体验",
                        "topic_tags": ["#荣耀Power2#"],
                    },
                )
            ]
        published_at = datetime(2026, 1, 19, 10, 0, tzinfo=UTC)
        return [
            RawRecord(
                external_id="thread:10001",
                record_type="THREAD",
                payload={
                    "title": "荣耀Power2 真实体验",
                    "content": "楼主真实正文",
                    "published_at": published_at,
                    "author_role_text": "LV7",
                    "source_url": "https://club.honor.com/cn/thread-10001-1-1.html",
                    "raw_data": {"topic_tags": ["#荣耀Power2#"]},
                },
            ),
            RawRecord(
                external_id="honor_post:20001",
                record_type="REPLY",
                payload={
                    "parent_external_id": "thread:10001",
                    "content": "官方真实回复",
                    "published_at": published_at,
                    "author_role_text": "荣耀答答团",
                    "source_url": "https://club.honor.com/cn/thread-10001-1-1.html#pid20001",
                    "raw_data": {},
                },
            ),
        ]

    def normalize_record(self, raw_record: RawRecord) -> NormalizedReview:
        role = "OFFICIAL" if raw_record.payload["author_role_text"] == "荣耀答答团" else "USER"
        record_type = "OFFICIAL_REPLY" if role == "OFFICIAL" else raw_record.record_type
        return NormalizedReview(
            external_id=raw_record.external_id,
            parent_external_id=raw_record.payload.get("parent_external_id"),
            record_type=record_type,
            title=raw_record.payload.get("title", ""),
            content=raw_record.payload["content"],
            published_at=raw_record.payload["published_at"],
            author_role=role,
            is_official=role == "OFFICIAL",
            source_url=raw_record.payload["source_url"],
            raw_data=raw_record.payload["raw_data"],
        )


@pytest.fixture
def honor_source_target(product: Product) -> SourceTarget:
    source, _ = DataSource.objects.update_or_create(
        code="HONOR_CLUB",
        defaults={"name": "荣耀俱乐部", "source_type": SourceType.COMMUNITY},
    )
    target, _ = SourceTarget.objects.update_or_create(
        source=source,
        name="荣耀Power2官方话题",
        defaults={
            "product": product,
            "target_type": TargetType.COMMUNITY,
            "target_url": "https://club.honor.com/cn/threadtopic-595-1.html",
            "external_id": "topic:595",
            "config_json": {"topic_id": 595, "max_topic_pages": 1, "max_threads": 10},
        },
    )
    return target


@pytest.mark.django_db
def test_runner_persists_checkpoint_and_deduplicates_second_run(
    honor_source_target: SourceTarget,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    collector = FixtureHonorCollector()
    monkeypatch.setattr("apps.collection.services.collection_runner.get_collector", lambda _source_code: collector)
    task = CollectionTask.objects.create(source_target=honor_source_target, requested_limit=1)

    first = run_collection(task.id)
    task.refresh_from_db()

    assert first.inserted_records == 2
    assert task.status == CollectionStatus.SUCCESS
    assert task.last_checkpoint == {"topic_page": 1, "thread_index": 1, "last_thread_id": "10001"}
    assert ReviewRecord.objects.count() == 2

    task.transition_to(CollectionStatus.PENDING)
    task.last_checkpoint = {}
    task.save(update_fields=("status", "last_checkpoint", "updated_at"))
    second = run_collection(task.id)
    task.refresh_from_db()

    assert second.inserted_records == 0
    assert second.skipped_records == 2
    assert task.skipped_count == 2
    assert ReviewRecord.objects.count() == 2
