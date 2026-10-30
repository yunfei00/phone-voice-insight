import json
from datetime import timedelta
from typing import Any

import pytest
from ai.providers.base import AIProvider, AIProviderError, AIProviderResponse
from ai.schemas.review_analysis import ReviewAnalysisInput
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.analysis.models import (
    AnalysisReviewRecord,
    AnalysisRun,
    OpinionAspect,
    StructuredAnalysis,
    StructuredRunStatus,
)
from apps.analysis.services.structured_engine import analyze_content
from apps.products.models import Product
from apps.reviews.models import (
    AuthorRole,
    GovernanceAIReview,
    RecordType,
    ReviewQuality,
    ReviewRecord,
)
from apps.sources.models import SourceTarget, TargetType


class StructuredProvider(AIProvider):
    provider_name = "fake-structured"
    model = "fake-v1"

    def __init__(self, outputs: list[str] | None = None) -> None:
        self.outputs = outputs or []
        self.calls = 0

    def analyze_review(
        self, request: ReviewAnalysisInput, *, prompt: str, validation_feedback: str = ""
    ) -> AIProviderResponse:
        del validation_feedback
        assert "不可信输入" in prompt
        self.calls += 1
        content = self.outputs.pop(0) if self.outputs else json.dumps(payload(request.content), ensure_ascii=False)
        return AIProviderResponse(self.provider_name, self.model, content, 12, 20, 30, 50)

    def check_connectivity(self):  # type: ignore[no-untyped-def]
        raise NotImplementedError


class TimeoutProvider(StructuredProvider):
    def analyze_review(self, request, *, prompt, validation_feedback=""):  # type: ignore[no-untyped-def]
        del request, prompt, validation_feedback
        raise AIProviderError("AI_TIMEOUT", "AI request timed out", retriable=True)


def test_structured_prompt_exists() -> None:
    from apps.analysis.services.structured_engine import _PROMPT_CANDIDATES, PROMPT_PATH, _prompt

    assert PROMPT_PATH.is_file(), f"Structured analysis prompt missing: {PROMPT_PATH}"
    assert PROMPT_PATH in _PROMPT_CANDIDATES
    rendered = _prompt()
    assert '"overall_sentiment"' in rendered
    assert '"BAT"' in rendered


def test_structured_batch_filter_accepts_null_optional_ids() -> None:
    from apps.analysis.structured_serializers import StructuredBatchCreateSerializer

    serializer = StructuredBatchCreateSerializer(
        data={"product_id": 1, "source_id": None, "max_items": 20, "dry_run": True}
    )

    assert serializer.is_valid(), serializer.errors
    assert serializer.validated_data["source_id"] is None


def payload(text: str) -> dict[str, Any]:
    evidence = "信号不稳定" if "信号不稳定" in text else text
    start = text.index(evidence)
    return {
        "schema_version": "1.0.0",
        "taxonomy_version": "1.0.0",
        "overall_sentiment": "NEGATIVE",
        "language": "zh-CN",
        "content_type": "COMMUNITY_REPLY",
        "relevance": "RELEVANT",
        "summary": "用户反馈通信体验问题",
        "model_mentions": [],
        "aspects": [
            {
                "business_domains": ["NET"],
                "aspect_code": "NET",
                "topic_code": "NET.CELLULAR",
                "sentiment": "NEGATIVE",
                "intent": "COMPLAINT",
                "issue_type": "RELIABILITY",
                "severity": "MEDIUM",
                "scenario": None,
                "trigger": None,
                "phenomenon": "信号不稳定",
                "target_product": None,
                "compared_products": [],
                "relation_type": "SELF",
                "evidence_text": evidence,
                "evidence_start": start,
                "evidence_end": start + len(evidence),
                "confidence": 0.9,
                "review_required": False,
            }
        ],
    }


@pytest.fixture
def review(product, source, source_target):  # type: ignore[no-untyped-def]
    return ReviewRecord.objects.create(
        product=product,
        source=source,
        source_target=source_target,
        external_id="reply-v1",
        record_type=RecordType.REPLY,
        title="",
        content="地下车库信号不稳定",
        content_hash="a" * 64,
        author_role=AuthorRole.USER,
        collected_at=timezone.now(),
        published_at=timezone.now(),
    )


@pytest.mark.django_db
def test_engine_persists_structured_result_and_aspect(review):  # type: ignore[no-untyped-def]
    run = analyze_content(review.id, StructuredProvider())
    assert run.status == StructuredRunStatus.SUCCEEDED
    assert run.structured_analysis.schema_valid
    assert run.structured_analysis.aspects.get().topic_code == "NET.CELLULAR"
    assert run.input_tokens == 20


@pytest.mark.django_db
def test_duplicate_analysis_is_idempotent(review):  # type: ignore[no-untyped-def]
    provider = StructuredProvider()
    first = analyze_content(review.id, provider)
    second = analyze_content(review.id, provider)
    assert first.id == second.id
    assert provider.calls == 1
    assert AnalysisRun.objects.count() == 1


@pytest.mark.django_db
def test_force_reanalysis_preserves_history(review):  # type: ignore[no-untyped-def]
    provider = StructuredProvider()
    first = analyze_content(review.id, provider)
    second = analyze_content(review.id, provider, force=True)
    first.refresh_from_db()
    assert second.id != first.id
    assert not first.is_current and second.is_current
    assert AnalysisRun.objects.count() == 2


@pytest.mark.django_db
def test_invalid_json_retries_with_limit(review):  # type: ignore[no-untyped-def]
    provider = StructuredProvider(["not-json", json.dumps(payload(review.content), ensure_ascii=False)])
    run = analyze_content(review.id, provider, max_retries=1)
    assert run.status == StructuredRunStatus.SUCCEEDED
    assert provider.calls == 2


@pytest.mark.django_db
def test_provider_timeout_records_safe_failure(review):  # type: ignore[no-untyped-def]
    run = analyze_content(review.id, TimeoutProvider())
    assert run.status == StructuredRunStatus.FAILED
    assert run.error_code == "AI_TIMEOUT"
    assert "key" not in run.error_message.lower()


@pytest.mark.django_db
def test_taxonomy_api(api_client):  # type: ignore[no-untyped-def]
    response = api_client.get("/api/v1/taxonomies/")
    assert response.status_code == 200
    assert response.data["taxonomy_version"] == "1.0.0"
    assert len(response.data["domains"]) == 15


@pytest.mark.django_db
def test_review_correction_replaces_aspects_and_keeps_history(api_client, review):  # type: ignore[no-untyped-def]
    run = analyze_content(review.id, StructuredProvider())
    corrected = payload(review.content)
    corrected["aspects"] = []
    corrected["overall_sentiment"] = "NEUTRAL"
    response = api_client.post(
        f"/api/v1/structured-analyses/{run.structured_analysis.id}/review/",
        {"corrected_result": corrected, "review_reason": "人工确认无有效观点"},
        format="json",
    )
    assert response.status_code == 200
    assert response.data["overall_sentiment"] == "NEUTRAL"
    assert response.data["aspects"] == []
    assert AnalysisReviewRecord.objects.filter(analysis=run.structured_analysis).count() == 1


def accept_for_final_corpus(review: ReviewRecord) -> None:
    quality, _ = ReviewQuality.objects.update_or_create(
        review=review,
        defaults={
            "eligible_for_ai": True,
            "is_official_content": False,
            "processor_version": "test",
            "processed_at": timezone.now(),
        },
    )
    GovernanceAIReview.objects.create(
        quality=quality,
        status=GovernanceAIReview.Status.ACCEPTED,
        rule_eligible=True,
        ai_eligible=True,
        input_hash="a" * 64,
    )


@pytest.mark.django_db
def test_aggregate_counts_are_deterministic(api_client, review):  # type: ignore[no-untyped-def]
    accept_for_final_corpus(review)
    analyze_content(review.id, StructuredProvider())
    response = api_client.get("/api/v1/structured-analyses/aggregates/")
    assert response.status_code == 200
    assert response.data["content_count"] == 1
    assert response.data["opinion_count"] == 1
    assert response.data["domain_distribution"] == [{"aspect_code": "NET", "count": 1}]
    assert response.data["high_frequency_clusters"] == [{"topic_code": "NET.CELLULAR", "count": 1}]
    assert response.data["independent_user_count"] is None
    assert response.data["product_issue_comparison"][0]["opinion_count"] == 1


@pytest.mark.django_db
def test_anomaly_windows_are_aggregated_correctly(api_client, product, source, source_target):  # type: ignore[no-untyped-def]
    now = timezone.now()
    for index in range(13):
        published_at = now - timedelta(days=2 if index < 5 else 14)
        item = ReviewRecord.objects.create(
            product=product,
            source=source,
            source_target=source_target,
            external_id=f"anomaly-{index}",
            record_type=RecordType.REPLY,
            title="",
            content="地下车库信号不稳定",
            content_hash=f"{index + 100:064x}",
            author_role=AuthorRole.USER,
            collected_at=now,
            published_at=published_at,
        )
        accept_for_final_corpus(item)
        analyze_content(item.id, StructuredProvider())

    response = api_client.get("/api/v1/structured-analyses/aggregates/")

    assert response.status_code == 200
    assert response.data["anomaly_candidates"] == [
        {
            "topic_code": "NET.CELLULAR",
            "observed_7d": 5,
            "baseline_28d": 8,
            "expected_7d": 2.0,
            "reason": "近7天数量至少5且达到历史周均的2倍",
        }
    ]


@pytest.mark.django_db
def test_aggregate_query_count_does_not_grow_with_topics(api_client, review):  # type: ignore[no-untyped-def]
    accept_for_final_corpus(review)
    run = analyze_content(review.id, StructuredProvider())
    analysis = run.structured_analysis
    OpinionAspect.objects.bulk_create(
        [
            OpinionAspect(
                analysis=analysis,
                business_domains=["NET"],
                aspect_code="NET",
                topic_code=f"NET.SYNTHETIC_{index:03d}",
                sentiment="NEGATIVE",
                intent="COMPLAINT",
                issue_type="RELIABILITY",
                severity="MEDIUM",
                scenario=None,
                trigger=None,
                phenomenon="网络体验异常",
                target_product=None,
                compared_products=[],
                relation_type="SELF",
                evidence_text="信号不稳定",
                evidence_start=4,
                evidence_end=9,
                confidence=0.9,
                review_required=False,
            )
            for index in range(100)
        ]
    )

    with CaptureQueriesContext(connection) as captured:
        response = api_client.get("/api/v1/structured-analyses/aggregates/")

    assert response.status_code == 200
    assert len(response.data["topic_distribution"]) == 101
    assert len(captured) <= 18


@pytest.mark.django_db
def test_aggregate_empty_dataset(api_client):  # type: ignore[no-untyped-def]
    response = api_client.get("/api/v1/structured-analyses/aggregates/")

    assert response.status_code == 200
    assert response.data["content_count"] == 0
    assert response.data["opinion_count"] == 0
    assert response.data["topic_distribution"] == []
    assert response.data["anomaly_candidates"] == []


@pytest.mark.django_db
def test_aggregate_product_filter_is_isolated(api_client, product, source, source_target):  # type: ignore[no-untyped-def]
    other_product = Product.objects.create(
        brand=product.brand,
        name="荣耀 Power",
        normalized_name="HONOR_POWER",
        series="Power",
    )
    other_target = SourceTarget.objects.create(
        source=source,
        product=other_product,
        name="另一个测试入口",
        target_type=TargetType.PRODUCT,
    )
    now = timezone.now()
    for index, (current_product, target) in enumerate(
        ((product, source_target), (other_product, other_target)), start=1
    ):
        item = ReviewRecord.objects.create(
            product=current_product,
            source=source,
            source_target=target,
            external_id=f"product-isolation-{index}",
            record_type=RecordType.REPLY,
            title="",
            content="地下车库信号不稳定",
            content_hash=f"{index + 300:064x}",
            author_role=AuthorRole.USER,
            collected_at=now,
            published_at=now,
        )
        accept_for_final_corpus(item)
        analyze_content(item.id, StructuredProvider())

    response = api_client.get(f"/api/v1/structured-analyses/aggregates/?product={other_product.id}")

    assert response.status_code == 200
    assert response.data["content_count"] == 1
    assert response.data["opinion_count"] == 1
    assert response.data["product_issue_comparison"] == [
        {
            "analysis__content__product__name": "荣耀 Power",
            "topic_code": "NET.CELLULAR",
            "content_count": 1,
            "opinion_count": 1,
        }
    ]


@pytest.mark.django_db
def test_batch_defaults_to_dry_run_and_does_not_call_ai(api_client, review):  # type: ignore[no-untyped-def]
    accept_for_final_corpus(review)
    response = api_client.post("/api/v1/structured-batches/", {"content_ids": [review.id]}, format="json")
    assert response.status_code == 201
    assert response.data["dry_run"] is True
    assert response.data["celery_task_id"] is None
    assert StructuredAnalysis.objects.count() == 0


@pytest.mark.django_db
def test_low_confidence_routes_to_review(review):  # type: ignore[no-untyped-def]
    raw = payload(review.content)
    raw["aspects"][0]["confidence"] = 0.5
    run = analyze_content(review.id, StructuredProvider([json.dumps(raw, ensure_ascii=False)]))
    assert run.status == StructuredRunStatus.REVIEW_REQUIRED
    assert StructuredAnalysis.objects.get(run=run).review_required


@pytest.mark.django_db
def test_invalid_taxonomy_fails_without_saving_analysis(review):  # type: ignore[no-untyped-def]
    raw = payload(review.content)
    raw["aspects"][0]["topic_code"] = "UNKNOWN.TOPIC"
    run = analyze_content(review.id, StructuredProvider([json.dumps(raw, ensure_ascii=False)]), max_retries=0)
    assert run.status == StructuredRunStatus.FAILED
    assert run.input_tokens == 20
    assert run.output_tokens == 30
    assert not StructuredAnalysis.objects.filter(run=run).exists()
    assert OpinionAspect.objects.count() == 0


@pytest.mark.django_db
def test_exact_evidence_repairs_invalid_model_offsets(review):  # type: ignore[no-untyped-def]
    raw = payload(review.content)
    raw["aspects"][0]["evidence_start"] = 0
    raw["aspects"][0]["evidence_end"] = 0

    run = analyze_content(review.id, StructuredProvider([json.dumps(raw, ensure_ascii=False)]), max_retries=0)

    assert run.status == StructuredRunStatus.SUCCEEDED
    aspect = run.structured_analysis.aspects.get()
    assert review.content[aspect.evidence_start : aspect.evidence_end] == aspect.evidence_text


@pytest.mark.django_db
def test_primary_aspect_is_added_to_business_domains(review):  # type: ignore[no-untyped-def]
    raw = payload(review.content)
    raw["aspects"][0]["business_domains"] = []

    run = analyze_content(review.id, StructuredProvider([json.dumps(raw, ensure_ascii=False)]), max_retries=0)

    assert run.status == StructuredRunStatus.SUCCEEDED
    assert run.structured_analysis.aspects.get().business_domains == ["NET"]


@pytest.mark.django_db
def test_topic_taxonomy_repairs_mismatched_primary_aspect(review):  # type: ignore[no-untyped-def]
    raw = payload(review.content)
    raw["aspects"][0]["aspect_code"] = "BAT"
    raw["aspects"][0]["business_domains"] = ["BAT"]

    run = analyze_content(review.id, StructuredProvider([json.dumps(raw, ensure_ascii=False)]), max_retries=0)

    assert run.status == StructuredRunStatus.SUCCEEDED
    aspect = run.structured_analysis.aspects.get()
    assert aspect.aspect_code == "NET"
    assert "NET" in aspect.business_domains
