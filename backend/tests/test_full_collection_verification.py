from collections import Counter
from datetime import UTC, datetime

import pytest
from collectors.base import (
    BaseCollector,
    CollectionRequest,
    CollectorError,
    CollectorTarget,
    NormalizedReview,
    RawPage,
    RawRecord,
    ValidationResult,
)

from apps.collection.models import (
    CollectionDiscoveredThread,
    CollectionStatus,
    CollectionTargetState,
    CollectionTask,
    CollectionTaskType,
)
from apps.collection.services.collection_runner import run_collection
from apps.products.models import Product
from apps.reviews.models import ReviewRecord
from apps.sources.models import DataSource, SourceTarget, SourceType, TargetType


class CompleteHonorCollector(BaseCollector):
    def __init__(self, *, permanent_failure: bool = False, invalid_topic: bool = False) -> None:
        self.permanent_failure = permanent_failure
        self.invalid_topic = invalid_topic
        self.fetches: Counter[tuple[str, str, int]] = Counter()

    def validate_target(self, target: CollectorTarget) -> ValidationResult:
        del target
        return ValidationResult(is_valid=True)

    def fetch_page(self, request: CollectionRequest) -> RawPage:
        kind = str(request.checkpoint.metadata["page_kind"])
        thread_id = str(request.checkpoint.metadata.get("thread_id", ""))
        page = request.checkpoint.page
        self.fetches[(kind, thread_id, page)] += 1
        if kind == "topic":
            if self.invalid_topic:
                content = "<html><title>提示信息</title></html>"
            else:
                pager = '<a href="threadtopic-595-2.html">2</a>'
                content = f'<div id="threadlist" data-topic-id="595"></div>{pager}'
        else:
            if thread_id == "2" and (self.permanent_failure or self.fetches[(kind, thread_id, page)] == 1):
                raise CollectorError("temporary network error", code="HTTP_5XX", retryable=True)
            pager = f'<a href="thread-{thread_id}-2-1.html">2</a>' if thread_id == "1" else ""
            content = f'<div class="wapFirstThread">thread {thread_id}</div>{pager}'
        return RawPage(
            content=content,
            fetched_at=datetime.now(UTC),
            checkpoint=request.checkpoint,
            metadata={**request.checkpoint.metadata, "request_url": request.target.target_url},
        )

    def parse_records(self, raw_page: RawPage) -> list[RawRecord]:
        kind = raw_page.metadata["page_kind"]
        if kind == "topic":
            page = raw_page.checkpoint.page
            thread_id = str(page)
            return [
                RawRecord(
                    external_id=f"thread_link:{thread_id}",
                    record_type="THREAD_LINK",
                    payload={
                        "thread_id": thread_id,
                        "thread_url": f"https://club.honor.com/cn/thread-{thread_id}-1-1.html",
                        "title": f"荣耀Power2 帖子 {thread_id}",
                        "topic_tags": ["荣耀Power2"],
                        "reply_count": "2" if thread_id == "1" else "1",
                    },
                )
            ]
        thread_id = str(raw_page.metadata["thread_id"])
        page = raw_page.checkpoint.page
        timestamp = datetime(2026, 10, 27, 10, 0, tzinfo=UTC)
        records = [
            RawRecord(
                external_id=f"thread:{thread_id}",
                record_type="THREAD",
                payload={
                    "title": f"荣耀Power2 帖子 {thread_id}",
                    "content": "真实正文",
                    "published_at": timestamp,
                    "source_url": f"https://club.honor.com/cn/thread-{thread_id}-{page}-1.html",
                    "raw_data": {"thread_id": thread_id, "topic_tags": ["荣耀Power2"]},
                },
            ),
            RawRecord(
                external_id=f"honor_post:{thread_id}01",
                record_type="REPLY",
                payload={
                    "parent_external_id": f"thread:{thread_id}",
                    "content": "跨页重复回复" if page == 2 else "普通回复",
                    "published_at": timestamp,
                    "author_role_text": "LV7",
                    "source_url": "https://club.honor.com/",
                    "raw_data": {"thread_id": thread_id},
                },
            ),
        ]
        if thread_id == "1" and page == 2:
            records.append(
                RawRecord(
                    external_id="honor_comment:102",
                    record_type="REPLY",
                    payload={
                        "parent_external_id": "honor_post:101",
                        "content": "楼中楼",
                        "published_at": timestamp,
                        "author_role_text": "荣耀答答团",
                        "source_url": "https://club.honor.com/",
                        "raw_data": {"thread_id": thread_id},
                    },
                )
            )
        return records

    def normalize_record(self, raw_record: RawRecord) -> NormalizedReview:
        official = raw_record.payload.get("author_role_text") == "荣耀答答团"
        return NormalizedReview(
            external_id=raw_record.external_id,
            parent_external_id=raw_record.payload.get("parent_external_id"),
            record_type="OFFICIAL_REPLY" if official else raw_record.record_type,
            title=str(raw_record.payload.get("title", "")),
            content=str(raw_record.payload.get("content", "")),
            published_at=raw_record.payload.get("published_at"),
            author_role="OFFICIAL" if official else "USER",
            is_official=official,
            source_url=str(raw_record.payload.get("source_url", "")),
            raw_data=dict(raw_record.payload.get("raw_data", {})),
        )


class FallbackTopicCollector(CompleteHonorCollector):
    def fetch_page(self, request: CollectionRequest) -> RawPage:
        page = super().fetch_page(request)
        if page.metadata["page_kind"] == "topic":
            return RawPage(
                content='<div id="threadlist" data-topic-id="595"></div>',
                fetched_at=page.fetched_at,
                checkpoint=page.checkpoint,
                metadata=page.metadata,
            )
        return page

    def parse_records(self, raw_page: RawPage) -> list[RawRecord]:
        if raw_page.metadata["page_kind"] == "topic" and raw_page.checkpoint.page > 1:
            return []
        return super().parse_records(raw_page)


@pytest.fixture
def full_target(product: Product) -> SourceTarget:
    source, _ = DataSource.objects.update_or_create(
        code="HONOR_CLUB",
        defaults={"name": "荣耀俱乐部", "source_type": SourceType.COMMUNITY},
    )
    return SourceTarget.objects.create(
        source=source,
        product=product,
        name="完整性测试话题",
        target_type=TargetType.COMMUNITY,
        target_url="https://club.honor.com/cn/threadtopic-595-1.html",
        config_json={
            "topic_id": 595,
            "full_chunk_topic_pages": 1,
            "full_chunk_threads": 1,
            "full_chunk_reply_pages": 1,
            "full_thread_max_attempts": 3,
        },
    )


def run_until_terminal(task: CollectionTask, *, max_chunks: int = 12) -> None:
    for _ in range(max_chunks):
        task.refresh_from_db()
        if task.status in (CollectionStatus.SUCCESS, CollectionStatus.FAILED):
            return
        run_collection(task.id)
    raise AssertionError("FULL did not finish within test chunk budget")


@pytest.mark.django_db
def test_full_scans_all_pages_retries_and_verifies_without_duplicates(
    full_target: SourceTarget,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    collector = CompleteHonorCollector()
    monkeypatch.setattr("apps.collection.services.collection_runner.get_collector", lambda _code: collector)
    task = CollectionTask.objects.create(source_target=full_target, task_type=CollectionTaskType.FULL)
    run_until_terminal(task)
    task.refresh_from_db()
    state = CollectionTargetState.objects.get(source_target=full_target)

    assert task.status == CollectionStatus.SUCCESS
    assert task.completion_verified and state.full_verified
    assert task.verification_report["expected_topic_pages"] == 2
    assert task.verification_report["scanned_topic_pages"] == 2
    assert task.verification_report["thread_details_success"] == 2
    assert task.verification_report["thread_details_failed"] == 0
    assert task.verification_report["retry_count"] == 1
    assert task.verification_report["reply_pages_scanned"] == 3
    assert ReviewRecord.objects.filter(record_type="THREAD").count() == 2
    assert ReviewRecord.objects.filter(external_id="honor_post:101").count() == 1
    assert ReviewRecord.objects.filter(record_type="OFFICIAL_REPLY").count() == 1
    assert task.runs.count() >= 3
    first_thread = CollectionDiscoveredThread.objects.get(task=task, thread_id="1")
    assert first_thread.expected_reply_pages == 2
    assert first_thread.next_reply_page == 3
    assert first_thread.reply_pages_scanned == 2

    record_count = ReviewRecord.objects.count()
    revalidation = CollectionTask.objects.create(
        source_target=full_target,
        task_type=CollectionTaskType.FULL,
    )
    run_until_terminal(revalidation)
    revalidation.refresh_from_db()
    assert revalidation.status == CollectionStatus.SUCCESS
    assert revalidation.completion_verified
    assert ReviewRecord.objects.count() == record_count


@pytest.mark.django_db
def test_unresolved_thread_fails_verification_but_keeps_collected_data(
    full_target: SourceTarget,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    collector = CompleteHonorCollector(permanent_failure=True)
    monkeypatch.setattr("apps.collection.services.collection_runner.get_collector", lambda _code: collector)
    task = CollectionTask.objects.create(source_target=full_target, task_type=CollectionTaskType.FULL)
    run_until_terminal(task)
    task.refresh_from_db()
    assert task.status == CollectionStatus.FAILED
    assert not task.completion_verified
    assert task.verification_report["unresolved_thread_ids"] == ["2"]
    assert ReviewRecord.objects.filter(external_id="thread:1").exists()


@pytest.mark.django_db
def test_full_uses_validated_empty_page_fallback_when_total_pages_are_missing(
    full_target: SourceTarget,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    collector = FallbackTopicCollector()
    monkeypatch.setattr("apps.collection.services.collection_runner.get_collector", lambda _code: collector)
    task = CollectionTask.objects.create(source_target=full_target, task_type=CollectionTaskType.FULL)

    run_until_terminal(task)
    task.refresh_from_db()

    assert task.status == CollectionStatus.SUCCESS
    assert task.completion_verified
    assert task.verification_report["expected_topic_pages"] == 1
    assert task.verification_report["scanned_topic_pages"] == 1
    assert collector.fetches[("topic", "", 2)] == 1


@pytest.mark.django_db
def test_invalid_topic_page_is_not_treated_as_empty_end(
    full_target: SourceTarget,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    collector = CompleteHonorCollector(invalid_topic=True)
    monkeypatch.setattr("apps.collection.services.collection_runner.get_collector", lambda _code: collector)
    task = CollectionTask.objects.create(source_target=full_target, task_type=CollectionTaskType.FULL)
    with pytest.raises(CollectorError, match="不是有效内容页"):
        run_collection(task.id)
    task.refresh_from_db()
    assert task.status == CollectionStatus.FAILED
    assert not task.completion_verified
