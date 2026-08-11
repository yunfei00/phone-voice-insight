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
from ai.validation.evidence_validator import (
    map_normalized_evidence_to_raw,
    reconcile_evidence_spans,
    validate_evidence,
)
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import override_settings
from django.utils import timezone
from pydantic import ValidationError
from rest_framework.test import APIClient

from apps.analysis.models import AnalysisBatch, AnalysisEvaluation, AnalysisResult
from apps.analysis.services.analysis_runner import analyze_corpus_item, run_analysis_batch
from apps.analysis.services.evaluation_samples import EvaluationSample, load_evaluation_sample
from apps.analysis.services.input_builder import build_review_analysis_input, compute_input_hash
from apps.analysis.services.prompt_loader import load_review_prompt
from apps.analysis.services.response_parser import parse_review_analysis_output
from apps.analysis.services.review_report import render_batch_review_markdown
from apps.analysis.services.sample_preview import SamplePreviewItem
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
    assert '"context_evidence_review_id"' in prompt


def test_review_analysis_v3_prompt_has_question_and_content_boundaries() -> None:
    prompt = load_review_prompt("review_analysis_v3")
    assert "为什么只有4G？" in prompt and "SIGNAL/NEUTRAL" in prompt
    assert "4G信号太差" in prompt and "SIGNAL/NEGATIVE" in prompt
    assert "相册里的 AI 作品不错" in prompt and "SYSTEM_BUG" in prompt
    assert "所有字段都必须存在" in prompt


@pytest.mark.parametrize("sample_version", ("phase5-poc-v1", "phase5-poc-v2", "phase5-poc-v3"))
def test_phase5_sample_manifest_contains_twenty_unique_review_ids(sample_version: str) -> None:
    sample = load_evaluation_sample(sample_version)
    assert sample.sample_version == sample_version and sample.seed == 20260808
    assert len(sample.review_ids) == 20 and len(set(sample.review_ids)) == 20


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


def test_evidence_normalization_maps_back_to_raw_contiguous_span() -> None:
    request = analysis_input(content="续航\u00a0  很好")
    output = valid_output(
        aspects=[
            {
                "aspect": "BATTERY",
                "sentiment": "POSITIVE",
                "sentiment_score": 0.8,
                "issue_category": "续航表现",
                "issue_summary": "续航很好",
                "usage_scenario": "",
                "evidence_text": "续航 很好",
                "context_dependent": False,
                "context_evidence_text": "",
                "context_evidence_review_id": "",
                "confidence": 0.9,
            }
        ]
    )
    reconciled = reconcile_evidence_spans(request, output, raw_content=request.content)
    assert reconciled.aspects[0].evidence_text == "续航\u00a0  很好"
    assert validate_evidence(request, reconciled, raw_content=request.content) == ()


def test_evidence_mapping_does_not_accept_punctuation_rewrite() -> None:
    assert map_normalized_evidence_to_raw("正常，有的人补丁没打。。所以大小不一样", "补丁没打。所以") is None


def test_analysis_validator_rejects_duplicates_and_product_mismatch() -> None:
    request = analysis_input()
    item = valid_output().aspects[0].model_dump(mode="json")
    output = valid_output(product_model="其他产品", aspects=[item, item])
    errors = validate_analysis(request, output)
    assert {error.field for error in errors} == {"product_model", "aspects"}


@pytest.mark.parametrize(
    ("content", "sentiment", "valid"),
    (
        ("为什么只有4G？", "NEUTRAL", True),
        ("为什么只有4G？", "NEGATIVE", False),
        ("信号太差了，为什么还是4G？", "NEGATIVE", True),
        ("充电慢不说，拍照也模糊是怎么回事？", "NEGATIVE", True),
        ("待机24小时电量直接掉了9%，怎么回事？", "NEGATIVE", True),
    ),
)
def test_question_sentiment_requires_explicit_negative_statement(
    content: str,
    sentiment: str,
    valid: bool,
) -> None:
    request = analysis_input(content=content, content_purpose="QUESTION")
    output = valid_output(
        aspects=[
            {
                "aspect": "SIGNAL",
                "sentiment": sentiment,
                "evidence_text": content,
                "context_dependent": False,
                "context_evidence_text": "",
                "context_evidence_review_id": "",
                "confidence": 0.9,
            }
        ]
    )

    errors = validate_analysis(request, output)

    assert (not errors) is valid


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


def test_openai_compatible_connectivity_uses_minimal_parseable_json(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        httpx,
        "post",
        lambda *_args, **_kwargs: FakeHttpResponse(
            200,
            {"choices": [{"message": {"content": '{"status":"ok"}'}}]},
        ),
    )
    result = provider().check_connectivity()
    assert result.provider == "openai_compatible"
    assert result.model == "model-2026-08"
    assert result.status == "ok" and result.request_id == "safe-request-id"


@override_settings(AI_PROVIDER="fake", AI_MODEL="fake-review-v1", AI_ALLOW_FAKE_PROVIDER=True)
def test_check_ai_command_is_network_free_with_fake_provider(capsys: pytest.CaptureFixture[str]) -> None:
    call_command("check_ai")
    assert json.loads(capsys.readouterr().out) == {
        "connectivity": "OK",
        "model": "fake-review-v1",
        "provider": "fake",
    }


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


class SchemaRetryProvider(FakeAIProvider):
    def __init__(self) -> None:
        super().__init__()
        self.calls = 0
        self.feedback = ""

    def analyze_review(
        self, request: ReviewAnalysisInput, *, prompt: str, validation_feedback: str = ""
    ) -> AIProviderResponse:
        self.calls += 1
        self.feedback = validation_feedback
        if self.calls == 1:
            return AIProviderResponse("fake", self.model, "not-json", 0)
        return super().analyze_review(request, prompt=prompt, validation_feedback=validation_feedback)


class AlwaysInvalidSchemaProvider(FakeAIProvider):
    def __init__(self) -> None:
        super().__init__()
        self.calls = 0

    def analyze_review(
        self, request: ReviewAnalysisInput, *, prompt: str, validation_feedback: str = ""
    ) -> AIProviderResponse:
        del request, prompt, validation_feedback
        self.calls += 1
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
def test_schema_failure_gets_one_repair_request_then_persists(product: Product) -> None:
    corpus = make_honor_corpus(product=product, content="屏幕挺不错", external_id="thread:schema-retry")
    provider_instance = SchemaRetryProvider()
    outcome = analyze_corpus_item(
        corpus,
        batch=None,
        prompt_version="review_analysis_v2",
        provider=provider_instance,
    )
    assert outcome.status == "SUCCESS" and outcome.attempts == 2 and outcome.retries == 1
    assert provider_instance.calls == 2 and "严格输出契约" in provider_instance.feedback


@pytest.mark.django_db
def test_second_schema_failure_is_persisted_without_more_retries(product: Product) -> None:
    corpus = make_honor_corpus(product=product, content="屏幕挺不错", external_id="thread:schema-failed")
    provider_instance = AlwaysInvalidSchemaProvider()
    outcome = analyze_corpus_item(
        corpus,
        batch=None,
        prompt_version="review_analysis_v2",
        provider=provider_instance,
    )
    assert outcome.result_id is not None
    result = AnalysisResult.objects.get(pk=outcome.result_id)
    assert outcome.error_code == "SCHEMA_VALIDATION_FAILED" and outcome.attempts == 2 and outcome.retries == 1
    assert provider_instance.calls == 2
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
            "context_correct": True,
            "hallucination": False,
            "reviewer_notes": "fixture review",
        },
        format="json",
    )
    assert response.status_code == 200
    assert AnalysisEvaluation.objects.filter(analysis=result, evidence_correct=True).exists()
    report = render_batch_review_markdown(batch)
    assert "Human evaluation status: NOT_EVALUATED" in report
    assert "- [ ] Aspect 正确" in report
    assert "- [ ] Context 正确  - [ ] Context 错误" in report
    assert "- [ ] Hallucination 有  - [ ] Hallucination 无" in report
    assert "Content Purpose:" in report and "normalized_text" in report
    assert "### 必要上下文" in report and "> N/A" in report
    assert "### AI结果" in report
    assert "nickname" not in report and "raw_data" not in report


@pytest.mark.django_db
def test_analysis_input_uses_cleaned_content_and_preserves_purpose(product: Product) -> None:
    corpus = make_honor_corpus(
        product=product,
        content="后盖开裂\n作者声明：作品含AI生成内容",
        external_id="thread:cleaned-ai-input",
    )

    request = build_review_analysis_input(corpus)

    assert request.content == "后盖开裂"
    assert request.content_purpose == "PRODUCT_EXPERIENCE"
    assert corpus.review.content.endswith("作者声明：作品含AI生成内容")


@pytest.mark.django_db
@override_settings(AI_PROVIDER="fake", AI_MODEL="fake-review-v1", AI_ALLOW_FAKE_PROVIDER=True)
def test_analysis_results_filter_by_fixed_sample(
    product: Product,
    api_client: APIClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = make_honor_corpus(product=product, content="续航很好", external_id="thread:sample-filter-1")
    second = make_honor_corpus(product=product, content="屏幕不错", external_id="thread:sample-filter-2")
    for corpus in (first, second):
        analyze_corpus_item(corpus, batch=None, prompt_version="review_analysis_v2")
    monkeypatch.setattr(
        "apps.analysis.filters.load_evaluation_sample",
        lambda _version: EvaluationSample("phase5-poc-v1", 20260808, (second.review_id,)),
    )
    response = api_client.get("/api/v1/analysis-results/?sample_version=phase5-poc-v1")
    assert response.status_code == 200
    assert response.json()["count"] == 1
    assert response.json()["results"][0]["review_id"] == second.review_id


@pytest.mark.django_db
def test_analysis_results_reject_unknown_sample(api_client: APIClient) -> None:
    response = api_client.get("/api/v1/analysis-results/?sample_version=unknown")
    assert response.status_code == 400
    assert response.json()["detail"]["sample_version"] == ["UNKNOWN_EVALUATION_SAMPLE"]


@pytest.mark.django_db
def test_phase5_v2_sample_preview_endpoint_never_runs_ai(
    api_client: APIClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "apps.analysis.views.load_sample_preview",
        lambda _version: [
            SamplePreviewItem(
                review_id=70,
                record_type="REPLY",
                current_content="我也是",
                necessary_context="父帖正文：升级后掉电特别快",
                experience_signal_reason="CONTEXT:BATTERY:掉电",
                candidate_aspects=("BATTERY",),
                content_purpose="PRODUCT_EXPERIENCE",
                context_required=True,
            )
        ],
    )
    response = api_client.get(
        "/api/v1/analysis-results/sample-preview/",
        {"sample_version": "phase5-poc-v2"},
    )
    assert response.status_code == 200
    assert response.json()["ai_status"] == "NOT_RUN"
    assert response.json()["count"] == 1
    assert response.json()["items"][0]["candidate_aspects"] == ["BATTERY"]


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
@override_settings(AI_PROVIDER="fake", AI_MODEL="fake-review-v1", AI_ALLOW_FAKE_PROVIDER=True)
def test_analyze_reviews_blocks_more_than_twenty_without_explicit_flag(
    product: Product,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    corpus = make_honor_corpus(product=product, content="屏幕挺不错", external_id="thread:large-run-guard")
    monkeypatch.setattr(
        "apps.analysis.management.commands.analyze_reviews.select_corpus_items",
        lambda *_args, **_kwargs: [corpus] * 21,
    )
    with pytest.raises(CommandError, match="LARGE_RUN_REQUIRES_ALLOW_LARGE_RUN"):
        call_command(
            "analyze_reviews",
            product="HONOR_POWER2",
            source="HONOR_CLUB",
            limit=21,
            prompt_version="review_analysis_v2",
        )
    assert AnalysisBatch.objects.count() == 0 and AnalysisResult.objects.count() == 0


@pytest.mark.django_db
@override_settings(AI_PROVIDER="openai_compatible", AI_MODEL="", AI_BASE_URL="", AI_API_KEY="")
def test_analyze_reviews_accepts_fixed_record_ids_in_order(
    product: Product,
    capsys: pytest.CaptureFixture[str],
) -> None:
    first = make_honor_corpus(product=product, content="屏幕挺不错", external_id="thread:fixed-first")
    second = make_honor_corpus(product=product, content="发热明显", external_id="thread:fixed-second")
    call_command(
        "analyze_reviews",
        product="HONOR_POWER2",
        source="HONOR_CLUB",
        record_ids=f"{second.review_id},{first.review_id}",
        prompt_version="review_analysis_v2",
        dry_run=True,
        show_selected_ids=True,
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["selected_review_ids"] == [second.review_id, first.review_id]
    assert payload["selected"] == 2


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
        "prompt_version": "review_analysis_v3",
        "configured": False,
        "concurrency": 2,
    }
    assert "super-secret-must-never-be-returned" not in response.content.decode()


@pytest.mark.django_db
def test_batch_api_requires_second_confirmation_above_twenty(
    product: Product,
    api_client: APIClient,
) -> None:
    corpus = make_honor_corpus(product=product, content="屏幕挺不错", external_id="thread:api-large-run")
    response = api_client.post(
        "/api/v1/analysis-batches/",
        {
            "product_id": product.id,
            "source_id": corpus.source_id,
            "prompt_version": "review_analysis_v2",
            "limit": 100,
        },
        format="json",
    )
    assert response.status_code == 400
    assert response.json()["error_code"] == "LARGE_RUN_REQUIRES_EXPLICIT_CONFIRMATION"
