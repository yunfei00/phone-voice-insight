import json
from typing import Any

import pytest
from ai.providers.base import AIProvider, AIProviderError, AIProviderResponse
from ai.schemas.review_analysis import ReviewAnalysisInput
from django.utils import timezone

from apps.analysis.models import (
    AnalysisReviewRecord,
    AnalysisRun,
    OpinionAspect,
    StructuredAnalysis,
    StructuredRunStatus,
)
from apps.analysis.services.structured_engine import analyze_content
from apps.reviews.models import AuthorRole, RecordType, ReviewRecord


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


@pytest.mark.django_db
def test_aggregate_counts_are_deterministic(api_client, review):  # type: ignore[no-untyped-def]
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
def test_batch_defaults_to_dry_run_and_does_not_call_ai(api_client, review):  # type: ignore[no-untyped-def]
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
    raw["aspects"][0]["topic_code"] = "BAT.CHARGING"
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
