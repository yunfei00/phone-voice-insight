# ruff: noqa: RUF001

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest
from ai.providers.base import AIProviderError, AIProviderResponse
from ai.providers.fake import FakeAIProvider
from ai.providers.openai_compatible import OpenAICompatibleProvider
from ai.schemas.review_analysis import ReviewAnalysisInput, ReviewAnalysisOutput
from ai.validation.analysis_validator import validate_analysis
from ai.validation.evidence_validator import validate_evidence
from django.core.management import call_command
from django.test import override_settings
from django.utils import timezone
from pydantic import ValidationError
from rest_framework.test import APIClient

from apps.analysis.models import AnalysisBatch, AnalysisEvaluation, AnalysisResult
from apps.analysis.services.analysis_runner import analyze_corpus_item, run_analysis_batch
from apps.analysis.services.input_builder import compute_input_hash
from apps.analysis.services.prompt_loader import load_review_prompt
from apps.analysis.services.response_parser import parse_review_analysis_output
from apps.products.models import Product
from apps.reviews.models import AnalysisCorpusItem, AuthorRole, RecordType, ReviewRecord
from apps.reviews.services.constants import CORPUS_VERSION
from apps.reviews.services.governance_pipeline import GovernanceProcessor
from apps.sources.models import DataSource, SourceTarget, SourceType, TargetType


def make_honor_corpus(
    *,
    product: Product,
    content: str,
    title: str = "荣耀Power2使用体验",
    record_type: str = RecordType.THREAD,
    parent: ReviewRecord | None = None,
    external_id: str | None = None,
) -> AnalysisCorpusItem:
    source, _ = DataSource.objects.get_or_create(
        code="HONOR_CLUB", defaults={"name": "荣耀俱乐部", "source_type": SourceType.COMMUNITY}
    )
    target, _ = SourceTarget.objects.get_or_create(
        source=source,
        product=product,
        name="荣耀 Power2 话题",
        defaults={"target_type": TargetType.COMMUNITY, "is_active": True},
    )
    external_id = external_id or f"test:{hashlib.sha256(content.encode()).hexdigest()[:12]}"
    review = ReviewRecord.objects.create(
        source=source,
        source_target=target,
        product=product,
        external_id=external_id,
        parent_external_id=parent.external_id if parent and parent.external_id else "",
        record_type=record_type,
        title=title if record_type == RecordType.THREAD else "",
        content=content,
        author_role=AuthorRole.USER,
        content_hash=hashlib.sha256(f"{external_id}:{content}".encode()).hexdigest(),
        raw_data={"device_source": "荣耀Power2"},
        published_at=datetime(2026, 8, 8, tzinfo=UTC),
        collected_at=timezone.now(),
    )
    GovernanceProcessor().process(review, persist=True, force=True)
    return AnalysisCorpusItem.objects.select_related("review", "quality", "product", "source").get(review=review)


def analysis_input(**overrides: Any) -> ReviewAnalysisInput:
    values: dict[str, Any] = {
        "review_id": "1",
        "product_model": "荣耀 Power2",
        "content": "屏幕挺不错",
        "title": "",
        "source": "HONOR_CLUB",
        "record_type": "REPLY",
        "author_role": "USER",
    }
    values.update(overrides)
    return ReviewAnalysisInput.model_validate(values)


def valid_output(**overrides: Any) -> ReviewAnalysisOutput:
    values: dict[str, Any] = {
        "product_model": "荣耀 Power2",
        "is_valid_content": True,
        "content_type": "COMMUNITY_REPLY",
        "aspects": [
            {
                "aspect": "DISPLAY",
                "sentiment": "POSITIVE",
                "sentiment_score": 0.8,
                "issue_category": "屏幕显示",
                "issue_summary": "用户认可屏幕显示",
                "usage_scenario": "",
                "evidence_text": "屏幕挺不错",
                "context_dependent": False,
                "context_evidence_text": "",
                "context_evidence_review_id": "",
                "confidence": 0.92,
            }
        ],
        "software_version": None,
        "usage_scenarios": [],
        "summary": "用户认可屏幕",
        "confidence": 0.92,
        "warnings": [],
    }
    values.update(overrides)
    return ReviewAnalysisOutput.model_validate(values)


def test_response_parser_accepts_json_and_markdown_fence() -> None:
    payload = valid_output().model_dump(mode="json")
    plain, _ = parse_review_analysis_output(json.dumps(payload, ensure_ascii=False))
    fenced, _ = parse_review_analysis_output(f"```json\n{json.dumps(payload, ensure_ascii=False)}\n```")
    assert plain == fenced


def test_prompt_loader_resolves_prompt_from_installed_ai_package() -> None:
    prompt = load_review_prompt("review_analysis_v2")
    assert prompt.startswith("# Review Analysis Prompt v2")
    assert "BATTERY" in prompt


@pytest.mark.parametrize(
    "content",
    (
        "not-json",
        json.dumps({**valid_output().model_dump(mode="json"), "unexpected": True}),
        json.dumps({**valid_output().model_dump(mode="json"), "aspects": [{"aspect": "UNKNOWN"}]}),
    ),
)
def test_response_parser_rejects_invalid_payloads(content: str) -> None:
    with pytest.raises((ValueError, ValidationError, json.JSONDecodeError)):
        parse_review_analysis_output(content)


def test_evidence_validator_rejects_hallucination_and_wrong_context() -> None:
    request = analysis_input(
        content="我也是",
        thread_review_id="10",
        thread_content="升级之后晚上待机掉电特别快",
        parent_review_id="10",
        parent_content="升级之后晚上待机掉电特别快",
    )
    output = valid_output(
        aspects=[
            {
                "aspect": "BATTERY",
                "sentiment": "NEGATIVE",
                "evidence_text": "我也遇到",
                "context_dependent": True,
                "context_evidence_text": "系统升级造成后台耗电",
                "context_evidence_review_id": "10",
                "confidence": 0.7,
            }
        ]
    )
    errors = validate_evidence(request, output)
    assert {error.field for error in errors} == {"evidence_text", "context_evidence_text"}


def test_analysis_validator_rejects_duplicates_and_product_mismatch() -> None:
    request = analysis_input()
    item = valid_output().aspects[0].model_dump(mode="json")
    output = valid_output(product_model="其他产品", aspects=[item, item])
    errors = validate_analysis(request, output)
    assert {error.field for error in errors} == {"product_model", "aspects"}


def test_analysis_validator_rejects_official_content_defensively() -> None:
    request = analysis_input(is_official=False, author_role="OFFICIAL", record_type="OFFICIAL_REPLY")
    errors = validate_analysis(request, valid_output())
    assert {error.field for error in errors} == {"is_official"}


class FakeHttpResponse:
    def __init__(self, status_code: int, payload: dict[str, Any] | None = None) -> None:
        self.status_code = status_code
        self._payload = payload or {}
        self.headers = {"x-request-id": "safe-request-id"}

    def json(self) -> dict[str, Any]:
        return self._payload


def provider() -> OpenAICompatibleProvider:
    return OpenAICompatibleProvider(
        base_url="https://provider.example/v1",
        api_key="secret-not-for-output",
        model="model-2026-08",
        timeout_seconds=5,
        temperature=0,
        max_output_tokens=1500,
    )


@pytest.mark.parametrize(
    ("status_code", "expected_code", "retriable"),
    ((429, "AI_RATE_LIMITED", True), (500, "AI_PROVIDER_5XX", True), (401, "AI_AUTHENTICATION_FAILED", False)),
)
def test_openai_compatible_maps_http_errors(
    monkeypatch: pytest.MonkeyPatch, status_code: int, expected_code: str, retriable: bool
) -> None:
    monkeypatch.setattr(httpx, "post", lambda *_args, **_kwargs: FakeHttpResponse(status_code))
    with pytest.raises(AIProviderError) as exc_info:
        provider().analyze_review(analysis_input(), prompt="prompt")
    assert exc_info.value.code == expected_code
    assert exc_info.value.retriable is retriable
    assert "secret-not-for-output" not in str(exc_info.value)


def test_openai_compatible_maps_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    def raise_timeout(*_args: object, **_kwargs: object) -> None:
        raise httpx.ReadTimeout("timeout")

    monkeypatch.setattr(httpx, "post", raise_timeout)
    with pytest.raises(AIProviderError, match="timed out") as exc_info:
        provider().analyze_review(analysis_input(), prompt="prompt")
    assert exc_info.value.code == "AI_TIMEOUT" and exc_info.value.retriable


def test_openai_compatible_returns_valid_content_and_usage(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = valid_output().model_dump(mode="json")
    monkeypatch.setattr(
        httpx,
        "post",
        lambda *_args, **_kwargs: FakeHttpResponse(
            200,
            {
                "choices": [{"message": {"content": json.dumps(payload, ensure_ascii=False)}}],
                "usage": {"prompt_tokens": 101, "completion_tokens": 42, "total_tokens": 143},
            },
        ),
    )
    response = provider().analyze_review(analysis_input(), prompt="prompt")
    assert response.provider == "openai_compatible"
    assert response.model == "model-2026-08"
    assert response.request_id == "safe-request-id"
    assert (response.prompt_tokens, response.completion_tokens, response.total_tokens) == (101, 42, 143)
    parsed, _ = parse_review_analysis_output(response.content)
    assert parsed == valid_output()


@pytest.mark.django_db
@override_settings(AI_PROVIDER="fake", AI_MODEL="fake-review-v1", AI_ALLOW_FAKE_PROVIDER=True)
def test_pipeline_persists_multi_aspect_and_skips_same_input(product: Product) -> None:
    corpus = make_honor_corpus(product=product, content="续航确实很强，就是打游戏太烫了")
    first = analyze_corpus_item(corpus, batch=None, prompt_version="review_analysis_v2")
    second = analyze_corpus_item(corpus, batch=None, prompt_version="review_analysis_v2")
    assert first.result_id is not None
    result = AnalysisResult.objects.get(pk=first.result_id)
    aspects = {(item.aspect, item.sentiment) for item in result.aspects.all()}
    assert first.status == "SUCCESS" and second.status == "SKIPPED"
    assert aspects == {("BATTERY", "POSITIVE"), ("HEATING", "NEGATIVE")}
    assert result.input_hash == compute_input_hash(corpus, prompt_version="review_analysis_v2")
    assert result.provider == "fake"


@pytest.mark.django_db
@override_settings(AI_PROVIDER="fake", AI_MODEL="fake-review-v1", AI_ALLOW_FAKE_PROVIDER=True)
def test_context_dependent_reply_uses_current_and_parent_evidence(product: Product) -> None:
    parent_corpus = make_honor_corpus(
        product=product,
        content="升级之后晚上待机掉电特别快",
        title="荣耀Power2升级耗电",
        external_id="thread:context-test",
    )
    reply_corpus = make_honor_corpus(
        product=product,
        content="我也是",
        record_type=RecordType.REPLY,
        parent=parent_corpus.review,
        external_id="reply:context-test",
    )
    outcome = analyze_corpus_item(reply_corpus, batch=None, prompt_version="review_analysis_v2")
    assert outcome.result_id is not None
    aspect = AnalysisResult.objects.get(pk=outcome.result_id).aspects.get()
    assert aspect.aspect == "BATTERY" and aspect.sentiment == "NEGATIVE"
    assert aspect.evidence_text == "我也是" and aspect.context_dependent
    assert aspect.context_evidence_text in parent_corpus.review.content
    assert aspect.context_evidence_review_id == str(parent_corpus.review_id)


@pytest.mark.django_db
@override_settings(AI_PROVIDER="fake", AI_MODEL="fake-review-v1", AI_ALLOW_FAKE_PROVIDER=True)
def test_fake_provider_does_not_hallucinate_aspects_and_distinguishes_fluency(product: Product) -> None:
    display = make_honor_corpus(product=product, content="屏幕挺不错", external_id="thread:display")
    fluency = make_honor_corpus(product=product, content="桌面滑动偶尔卡一下", external_id="thread:fluency")
    game = make_honor_corpus(product=product, content="游戏掉帧严重", external_id="thread:game")
    for corpus in (display, fluency, game):
        analyze_corpus_item(corpus, batch=None, prompt_version="review_analysis_v2")
    assert list(display.review.analyses.get().aspects.values_list("aspect", flat=True)) == ["DISPLAY"]
    assert list(fluency.review.analyses.get().aspects.values_list("aspect", flat=True)) == ["SYSTEM_FLUENCY"]
    assert list(game.review.analyses.get().aspects.values_list("aspect", flat=True)) == ["PERFORMANCE"]


class EvidenceRetryProvider(FakeAIProvider):
    def __init__(self) -> None:
        super().__init__()
        self.calls = 0

    def analyze_review(
        self, request: ReviewAnalysisInput, *, prompt: str, validation_feedback: str = ""
    ) -> AIProviderResponse:
        self.calls += 1
        response = super().analyze_review(request, prompt=prompt, validation_feedback=validation_feedback)
        if self.calls == 1:
            payload = json.loads(response.content)
            payload["aspects"][0]["evidence_text"] = "不存在的幻觉证据"
            return AIProviderResponse("fake", self.model, json.dumps(payload, ensure_ascii=False), 0)
        return response


@pytest.mark.django_db
def test_evidence_failure_retries_once_then_persists(product: Product) -> None:
    corpus = make_honor_corpus(product=product, content="掉电很快", external_id="thread:evidence-retry")
    provider_instance = EvidenceRetryProvider()
    outcome = analyze_corpus_item(
        corpus,
        batch=None,
        prompt_version="review_analysis_v2",
        provider=provider_instance,
    )
    assert outcome.status == "SUCCESS" and outcome.attempts == 2 and outcome.retries == 1
    assert provider_instance.calls == 2


class AlwaysInvalidEvidenceProvider(FakeAIProvider):
    def __init__(self) -> None:
        super().__init__()
        self.calls = 0

    def analyze_review(
        self, request: ReviewAnalysisInput, *, prompt: str, validation_feedback: str = ""
    ) -> AIProviderResponse:
        self.calls += 1
        response = super().analyze_review(request, prompt=prompt, validation_feedback=validation_feedback)
        payload = json.loads(response.content)
        payload["aspects"][0]["evidence_text"] = "不存在于原文的证据"
        return AIProviderResponse("fake", self.model, json.dumps(payload, ensure_ascii=False), 0)


class RetriableThenSuccessProvider(FakeAIProvider):
    def __init__(self) -> None:
        super().__init__()
        self.calls = 0

    def analyze_review(
        self, request: ReviewAnalysisInput, *, prompt: str, validation_feedback: str = ""
    ) -> AIProviderResponse:
        self.calls += 1
        if self.calls <= 2:
            raise AIProviderError("AI_PROVIDER_5XX", "safe provider failure", retriable=True)
        return super().analyze_review(request, prompt=prompt, validation_feedback=validation_feedback)


class InvalidSchemaProvider(FakeAIProvider):
    def analyze_review(
        self, request: ReviewAnalysisInput, *, prompt: str, validation_feedback: str = ""
    ) -> AIProviderResponse:
        del request, prompt, validation_feedback
        return AIProviderResponse("fake", self.model, "not-json", 0)


@pytest.mark.django_db
def test_second_evidence_failure_is_persisted_without_more_retries(product: Product) -> None:
    corpus = make_honor_corpus(product=product, content="掉电很快", external_id="thread:evidence-failed")
    provider_instance = AlwaysInvalidEvidenceProvider()
    outcome = analyze_corpus_item(
        corpus,
        batch=None,
        prompt_version="review_analysis_v2",
        provider=provider_instance,
    )
    assert outcome.result_id is not None
    result = AnalysisResult.objects.get(pk=outcome.result_id)
    assert outcome.status == "FAILED" and outcome.error_code == "EVIDENCE_VALIDATION_FAILED"
    assert provider_instance.calls == 2 and result.attempt_count == 2 and result.retry_count == 1
    assert result.raw_result == {} and not result.aspects.exists()


@pytest.mark.django_db
@override_settings(AI_MAX_RETRIES=2)
def test_retriable_provider_failure_uses_bounded_retry(product: Product, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("apps.analysis.services.analysis_runner.time.sleep", lambda _seconds: None)
    corpus = make_honor_corpus(product=product, content="屏幕挺不错", external_id="thread:provider-retry")
    provider_instance = RetriableThenSuccessProvider()
    outcome = analyze_corpus_item(
        corpus,
        batch=None,
        prompt_version="review_analysis_v2",
        provider=provider_instance,
    )
    assert outcome.status == "SUCCESS" and outcome.attempts == 3 and outcome.retries == 2
    assert provider_instance.calls == 3


@pytest.mark.django_db
def test_schema_failure_is_not_retried_and_is_persisted(product: Product) -> None:
    corpus = make_honor_corpus(product=product, content="屏幕挺不错", external_id="thread:schema-failed")
    provider_instance = InvalidSchemaProvider()
    outcome = analyze_corpus_item(
        corpus,
        batch=None,
        prompt_version="review_analysis_v2",
        provider=provider_instance,
    )
    assert outcome.result_id is not None
    result = AnalysisResult.objects.get(pk=outcome.result_id)
    assert outcome.error_code == "SCHEMA_VALIDATION_FAILED" and outcome.attempts == 1 and outcome.retries == 0
    assert result.status == "FAILED" and result.error_message == "AI response did not match the required schema"


@pytest.mark.django_db
@override_settings(AI_PROVIDER="openai_compatible", AI_MODEL="", AI_BASE_URL="", AI_API_KEY="")
def test_ineligible_corpus_is_skipped_before_provider_lookup(product: Product) -> None:
    corpus = make_honor_corpus(product=product, content="支持一下", external_id="thread:ineligible")
    corpus.eligible = False
    corpus.save(update_fields=("eligible", "updated_at"))
    outcome = analyze_corpus_item(corpus, batch=None, prompt_version="review_analysis_v2")
    assert outcome.status == "SKIPPED" and outcome.error_code == "CORPUS_ITEM_NOT_ELIGIBLE"
    assert AnalysisResult.objects.count() == 0


@pytest.mark.django_db
@override_settings(AI_PROVIDER="openai_compatible", AI_MODEL="", AI_BASE_URL="", AI_API_KEY="")
def test_out_of_scope_product_is_skipped_before_provider_lookup(product: Product) -> None:
    corpus = make_honor_corpus(product=product, content="屏幕挺不错", external_id="thread:other-product")
    product.normalized_name = "OTHER_PRODUCT"
    product.save(update_fields=("normalized_name", "updated_at"))
    corpus.refresh_from_db()
    outcome = analyze_corpus_item(corpus, batch=None, prompt_version="review_analysis_v2")
    assert outcome.status == "SKIPPED" and outcome.error_code == "PHASE5_TARGET_ONLY"
    assert AnalysisResult.objects.count() == 0


@pytest.mark.django_db
def test_batch_api_rejects_non_honor_source(product: Product, source: DataSource, api_client: APIClient) -> None:
    response = api_client.post(
        "/api/v1/analysis-batches/",
        {
            "product_id": product.id,
            "source_id": source.id,
            "prompt_version": "review_analysis_v2",
            "limit": 20,
        },
        format="json",
    )
    assert response.status_code == 400 and response.json()["error_code"] == "PHASE5_TARGET_ONLY"


@pytest.mark.django_db
@override_settings(AI_PROVIDER="fake", AI_MODEL="fake-review-v1", AI_ALLOW_FAKE_PROVIDER=True)
def test_batch_statistics_and_evaluation_api(product: Product, api_client: APIClient) -> None:
    corpora = [
        make_honor_corpus(product=product, content="续航很好", external_id="thread:batch-1"),
        make_honor_corpus(product=product, content="屏幕不错", external_id="thread:batch-2"),
    ]
    batch = AnalysisBatch.objects.create(
        product=product,
        source=corpora[0].source,
        corpus_version=CORPUS_VERSION,
        provider="fake",
        model_name="fake-review-v1",
        prompt_version="review_analysis_v2",
        requested_count=2,
    )
    outcomes = run_analysis_batch(batch, corpus_items=corpora)
    batch.refresh_from_db()
    assert len(outcomes) == 2 and batch.success_count == 2 and batch.failed_count == 0
    result = AnalysisResult.objects.first()
    assert result is not None
    response = api_client.post(
        f"/api/v1/analysis-results/{result.id}/evaluate/",
        {
            "aspect_correct": True,
            "sentiment_correct": True,
            "issue_correct": True,
            "scenario_correct": True,
            "evidence_correct": True,
            "hallucination": False,
            "reviewer_notes": "fixture review",
        },
        format="json",
    )
    assert response.status_code == 200
    assert AnalysisEvaluation.objects.filter(analysis=result, evidence_correct=True).exists()


@pytest.mark.django_db
@override_settings(AI_PROVIDER="openai_compatible", AI_MODEL="", AI_BASE_URL="", AI_API_KEY="")
def test_analyze_reviews_dry_run_never_requires_provider(product: Product, capsys: pytest.CaptureFixture[str]) -> None:
    make_honor_corpus(product=product, content="续航很好", external_id="thread:dry-run")
    call_command(
        "analyze_reviews",
        product="HONOR_POWER2",
        source="HONOR_CLUB",
        limit=20,
        prompt_version="review_analysis_v2",
        dry_run=True,
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["dry_run"] is True and payload["selected"] == 1
    assert payload["model"] == "NOT_CONFIGURED"
    assert AnalysisResult.objects.count() == 0


@pytest.mark.django_db
@override_settings(
    AI_PROVIDER="openai_compatible",
    AI_MODEL="",
    AI_BASE_URL="",
    AI_API_KEY="super-secret-must-never-be-returned",
)
def test_ai_configuration_endpoint_never_returns_api_key(api_client: APIClient) -> None:
    response = api_client.get("/api/v1/analysis-batches/configuration/")
    assert response.status_code == 200
    assert response.json() == {
        "provider": "openai_compatible",
        "model": "NOT_CONFIGURED",
        "prompt_version": "review_analysis_v2",
        "configured": False,
        "concurrency": 2,
    }
    assert "super-secret-must-never-be-returned" not in response.content.decode()
