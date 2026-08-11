"""Idempotent, evidence-validated structured analysis pipeline."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from ai.providers import AIProvider, AIProviderError, get_ai_provider
from ai.schemas.review_analysis import ReviewAnalysisOutput
from ai.validation.analysis_validator import validate_analysis
from ai.validation.evidence_validator import validate_evidence
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from pydantic import ValidationError

from apps.analysis.models import (
    AnalysisBatch,
    AnalysisBatchStatus,
    AnalysisResult,
    AnalysisStatus,
    AspectResult,
)
from apps.analysis.services.input_builder import (
    build_review_analysis_input,
    compute_input_hash,
    is_phase5_target,
)
from apps.analysis.services.prompt_loader import load_review_prompt
from apps.analysis.services.response_parser import parse_review_analysis_output
from apps.reviews.models import AnalysisCorpusItem

logger = logging.getLogger(__name__)
ANALYSIS_BATCH_SIZE = 10


@dataclass(frozen=True)
class AnalysisOutcome:
    review_id: int
    status: str
    result_id: int | None
    error_code: str = ""
    attempts: int = 0
    retries: int = 0
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None


def _safe_error_message(code: str) -> str:
    messages = {
        "AI_NOT_CONFIGURED": "AI provider configuration is incomplete",
        "SCHEMA_VALIDATION_FAILED": "AI response did not match the required schema",
        "ANALYSIS_VALIDATION_FAILED": "AI response failed business validation",
        "EVIDENCE_VALIDATION_FAILED": "AI response evidence was not verbatim or traceable",
        "PERSISTENCE_FAILED": "Validated AI response could not be persisted",
    }
    return messages.get(code, "AI analysis failed")


def _nullable_add(current: int | None, value: int | None) -> int | None:
    if value is None:
        return current
    return (current or 0) + value


def _persist_success(
    result: AnalysisResult,
    *,
    output: ReviewAnalysisOutput,
    raw_result: dict[str, object],
    provider_name: str,
    model: str,
    attempts: int,
    retries: int,
    latency_ms: int,
    prompt_tokens: int | None,
    completion_tokens: int | None,
    total_tokens: int | None,
    request_id: str,
) -> None:
    with transaction.atomic():
        result.status = AnalysisStatus.SUCCESS
        result.provider = provider_name
        result.model_name = model
        result.model_version = model
        result.is_valid_content = output.is_valid_content
        result.confidence = Decimal(str(output.confidence))
        result.summary = output.summary
        result.raw_result = raw_result
        result.error_code = ""
        result.error_message = ""
        result.attempt_count = attempts
        result.retry_count = retries
        result.latency_ms = latency_ms
        result.prompt_tokens = prompt_tokens
        result.completion_tokens = completion_tokens
        result.total_tokens = total_tokens
        result.provider_request_id = request_id
        result.analyzed_at = timezone.now()
        result.save()
        result.aspects.all().delete()
        AspectResult.objects.bulk_create(
            [
                AspectResult(
                    analysis=result,
                    aspect=item.aspect.value,
                    sentiment=item.sentiment.value,
                    sentiment_score=Decimal(str(item.sentiment_score)) if item.sentiment_score is not None else None,
                    issue_category=item.issue_category,
                    issue_summary=item.issue_summary,
                    usage_scenario=item.usage_scenario,
                    evidence_text=item.evidence_text,
                    context_dependent=item.context_dependent,
                    context_evidence_text=item.context_evidence_text,
                    context_evidence_review_id=item.context_evidence_review_id,
                    confidence=Decimal(str(item.confidence)),
                )
                for item in output.aspects
            ]
        )


def _persist_failure(
    result: AnalysisResult,
    *,
    code: str,
    attempts: int,
    retries: int,
    latency_ms: int | None,
    token_usage: tuple[int | None, int | None, int | None],
) -> None:
    result.status = AnalysisStatus.FAILED
    result.error_code = code
    result.error_message = _safe_error_message(code)
    result.raw_result = {}
    result.attempt_count = attempts
    result.retry_count = retries
    result.latency_ms = latency_ms
    result.prompt_tokens, result.completion_tokens, result.total_tokens = token_usage
    result.analyzed_at = timezone.now()
    result.save()
    result.aspects.all().delete()


def analyze_corpus_item(
    corpus_item: AnalysisCorpusItem,
    *,
    batch: AnalysisBatch | None,
    prompt_version: str,
    provider: AIProvider | None = None,
    force: bool = False,
    retry_failed: bool = False,
) -> AnalysisOutcome:
    if not corpus_item.eligible or not corpus_item.quality.eligible_for_ai:
        return AnalysisOutcome(corpus_item.review_id, "SKIPPED", None, "CORPUS_ITEM_NOT_ELIGIBLE")
    if not is_phase5_target(corpus_item):
        return AnalysisOutcome(corpus_item.review_id, "SKIPPED", None, "PHASE5_TARGET_ONLY")
    prompt = load_review_prompt(prompt_version)
    request = build_review_analysis_input(corpus_item)
    input_hash = compute_input_hash(corpus_item, prompt_version=prompt_version)
    provider = provider or get_ai_provider()
    if not force:
        successful = AnalysisResult.objects.filter(
            review_id=corpus_item.review_id,
            model_name=provider.model,
            prompt_version=prompt_version,
            input_hash=input_hash,
            status=AnalysisStatus.SUCCESS,
        ).first()
        if successful is not None:
            return AnalysisOutcome(corpus_item.review_id, "SKIPPED", successful.id)
    existing = AnalysisResult.objects.filter(
        review_id=corpus_item.review_id,
        provider=provider.provider_name,
        model_name=provider.model,
        prompt_version=prompt_version,
        input_hash=input_hash,
    ).first()
    if existing is not None and not force:
        if existing.status == AnalysisStatus.FAILED and not retry_failed:
            return AnalysisOutcome(corpus_item.review_id, "SKIPPED", existing.id, existing.error_code)
    result = existing or AnalysisResult.objects.create(
        review=corpus_item.review,
        corpus_item=corpus_item,
        batch=batch,
        status=AnalysisStatus.PENDING,
        provider=provider.provider_name,
        model_name=provider.model,
        model_version=provider.model,
        prompt_version=prompt_version,
        input_hash=input_hash,
    )
    if existing is not None:
        result.batch = batch
        result.corpus_item = corpus_item
        result.status = AnalysisStatus.PENDING
        result.save(update_fields=("batch", "corpus_item", "status", "updated_at"))

    attempts = retries = latency_ms = 0
    prompt_tokens = completion_tokens = total_tokens = None
    validation_feedback = ""
    schema_retry_used = False
    evidence_retry_used = False
    while True:
        attempts += 1
        try:
            response = provider.analyze_review(
                request,
                prompt=prompt,
                validation_feedback=validation_feedback,
            )
        except AIProviderError as exc:
            if exc.retriable and retries < settings.AI_MAX_RETRIES:
                retries += 1
                time.sleep(min(2 ** (retries - 1), 8))
                continue
            _persist_failure(
                result,
                code=exc.code,
                attempts=attempts,
                retries=retries,
                latency_ms=latency_ms or None,
                token_usage=(prompt_tokens, completion_tokens, total_tokens),
            )
            return AnalysisOutcome(corpus_item.review_id, "FAILED", result.id, exc.code, attempts, retries)
        latency_ms += response.latency_ms
        prompt_tokens = _nullable_add(prompt_tokens, response.prompt_tokens)
        completion_tokens = _nullable_add(completion_tokens, response.completion_tokens)
        total_tokens = _nullable_add(total_tokens, response.total_tokens)
        try:
            output, raw_result = parse_review_analysis_output(response.content)
        except (ValueError, ValidationError):
            if not schema_retry_used and retries < settings.AI_MAX_RETRIES:
                schema_retry_used = True
                retries += 1
                validation_feedback = (
                    "返回内容不是符合严格输出契约的 JSON, 所有必填字段、字段类型和枚举值必须与系统提示一致。"
                )
                continue
            code = "SCHEMA_VALIDATION_FAILED"
            _persist_failure(
                result,
                code=code,
                attempts=attempts,
                retries=retries,
                latency_ms=latency_ms,
                token_usage=(prompt_tokens, completion_tokens, total_tokens),
            )
            return AnalysisOutcome(corpus_item.review_id, "FAILED", result.id, code, attempts, retries)
        business_errors = validate_analysis(request, output)
        if business_errors:
            code = "ANALYSIS_VALIDATION_FAILED"
            _persist_failure(
                result,
                code=code,
                attempts=attempts,
                retries=retries,
                latency_ms=latency_ms,
                token_usage=(prompt_tokens, completion_tokens, total_tokens),
            )
            return AnalysisOutcome(corpus_item.review_id, "FAILED", result.id, code, attempts, retries)
        evidence_errors = validate_evidence(request, output)
        if evidence_errors and not evidence_retry_used and retries < settings.AI_MAX_RETRIES:
            evidence_retry_used = True
            retries += 1
            validation_feedback = "; ".join(error.message for error in evidence_errors)[:500]
            continue
        if evidence_errors:
            code = "EVIDENCE_VALIDATION_FAILED"
            _persist_failure(
                result,
                code=code,
                attempts=attempts,
                retries=retries,
                latency_ms=latency_ms,
                token_usage=(prompt_tokens, completion_tokens, total_tokens),
            )
            return AnalysisOutcome(corpus_item.review_id, "FAILED", result.id, code, attempts, retries)
        try:
            _persist_success(
                result,
                output=output,
                raw_result=raw_result,
                provider_name=response.provider,
                model=response.model,
                attempts=attempts,
                retries=retries,
                latency_ms=latency_ms,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total_tokens,
                request_id=response.request_id,
            )
        except Exception:
            logger.exception("analysis_persistence_failed review_id=%s", corpus_item.review_id)
            code = "PERSISTENCE_FAILED"
            _persist_failure(
                result,
                code=code,
                attempts=attempts,
                retries=retries,
                latency_ms=latency_ms,
                token_usage=(prompt_tokens, completion_tokens, total_tokens),
            )
            return AnalysisOutcome(corpus_item.review_id, "FAILED", result.id, code, attempts, retries)
        logger.info(
            "analysis_complete review_id=%s provider=%s model=%s prompt_version=%s latency_ms=%s status=SUCCESS",
            corpus_item.review_id,
            response.provider,
            response.model,
            prompt_version,
            latency_ms,
        )
        return AnalysisOutcome(
            corpus_item.review_id,
            "SUCCESS",
            result.id,
            attempts=attempts,
            retries=retries,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
        )


def run_analysis_batch(
    batch: AnalysisBatch,
    *,
    corpus_items: list[AnalysisCorpusItem],
    force: bool = False,
    retry_failed: bool = False,
) -> list[AnalysisOutcome]:
    provider = get_ai_provider()
    batch.status = AnalysisBatchStatus.RUNNING
    batch.started_at = timezone.now()
    batch.error_message = ""
    batch.save(update_fields=("status", "started_at", "error_message", "updated_at"))
    outcomes: list[AnalysisOutcome] = []
    for offset in range(0, len(corpus_items), ANALYSIS_BATCH_SIZE):
        for corpus_item in corpus_items[offset : offset + ANALYSIS_BATCH_SIZE]:
            outcomes.append(
                analyze_corpus_item(
                    corpus_item,
                    batch=batch,
                    prompt_version=batch.prompt_version,
                    provider=provider,
                    force=force,
                    retry_failed=retry_failed,
                )
            )
    batch.success_count = sum(outcome.status == "SUCCESS" for outcome in outcomes)
    batch.failed_count = sum(outcome.status == "FAILED" for outcome in outcomes)
    batch.skipped_count = sum(outcome.status == "SKIPPED" for outcome in outcomes)
    batch.retry_count = sum(outcome.retries for outcome in outcomes)
    for field in ("prompt_tokens", "completion_tokens", "total_tokens"):
        values = [getattr(outcome, field) for outcome in outcomes if getattr(outcome, field) is not None]
        setattr(batch, field, sum(values) if values else None)
    if batch.failed_count and batch.success_count:
        batch.status = AnalysisBatchStatus.PARTIAL
    elif batch.failed_count:
        batch.status = AnalysisBatchStatus.FAILED
    else:
        batch.status = AnalysisBatchStatus.SUCCESS
    batch.finished_at = timezone.now()
    batch.save()
    return outcomes


def error_counts(outcomes: list[AnalysisOutcome]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for outcome in outcomes:
        if outcome.error_code:
            counts[outcome.error_code] = counts.get(outcome.error_code, 0) + 1
    return dict(sorted(counts.items()))


def outcome_dict(outcome: AnalysisOutcome) -> dict[str, Any]:
    return {
        "review_id": outcome.review_id,
        "status": outcome.status,
        "result_id": outcome.result_id,
        "error_code": outcome.error_code,
        "attempts": outcome.attempts,
        "retries": outcome.retries,
    }
