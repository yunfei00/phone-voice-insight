"""V1 结构化分析执行服务；不在导入或启动时发起任何模型调用。"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from ai.providers import AIProvider, AIProviderError
from ai.schemas.review_analysis import ReviewAnalysisInput
from ai.schemas.structured_analysis import SCHEMA_VERSION, StructuredAnalysisPayload
from ai.taxonomy import TAXONOMY_VERSION
from ai.validation import StructuredValidationResult, validate_structured_payload
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.analysis.models import AnalysisRun, OpinionAspect, StructuredAnalysis, StructuredRunStatus
from apps.reviews.models import ReviewRecord

PROMPT_VERSION = "structured_analysis_v1"
_ROOT = Path(__file__).resolve().parents[4]
_FENCE = re.compile(r"^\s*```(?:json)?\s*(.*?)\s*```\s*$", re.DOTALL | re.IGNORECASE)


def _prompt() -> str:
    return (_ROOT / "prompts" / f"{PROMPT_VERSION}.md").read_text(encoding="utf-8")


def _provider_input(review: ReviewRecord) -> ReviewAnalysisInput:
    return ReviewAnalysisInput(
        review_id=str(review.id),
        product_model=review.product.name,
        content=review.content,
        title=review.title or None,
        source=review.source.code,
        record_type=review.record_type,
        author_role=review.author_role,
        is_official=review.is_official,
        rating=float(review.rating) if review.rating is not None else None,
        software_version=review.software_version or None,
        published_at=review.published_at.isoformat() if review.published_at else None,
    )


def _identity(review: ReviewRecord, provider: AIProvider) -> tuple[str, str]:
    input_hash = hashlib.sha256(f"{review.title}\x1f{review.content}".encode()).hexdigest()
    material = "\x1f".join(
        (input_hash, provider.provider_name, provider.model, PROMPT_VERSION, TAXONOMY_VERSION, SCHEMA_VERSION)
    )
    return input_hash, hashlib.sha256(material.encode()).hexdigest()


def _decode(content: str) -> dict[str, object]:
    match = _FENCE.fullmatch(content)
    parsed = json.loads(match.group(1) if match else content.strip())
    if not isinstance(parsed, dict):
        raise ValueError("AI response must be a JSON object")
    return parsed


def _create_run(
    review: ReviewRecord, provider: AIProvider, *, force: bool, batch_id: int | None
) -> tuple[AnalysisRun, bool]:
    input_hash, configuration_hash = _identity(review, provider)
    with transaction.atomic():
        ReviewRecord.objects.select_for_update().get(pk=review.pk)
        current = AnalysisRun.objects.filter(
            content=review, configuration_hash=configuration_hash, is_current=True
        ).first()
        if current and not force:
            return current, False
        if current:
            current.is_current = False
            current.save(update_fields=("is_current", "updated_at"))
        try:
            run = AnalysisRun.objects.create(
                content=review,
                batch_id=batch_id,
                status=StructuredRunStatus.RUNNING,
                provider=provider.provider_name,
                model=provider.model,
                input_hash=input_hash,
                configuration_hash=configuration_hash,
                started_at=timezone.now(),
            )
        except IntegrityError:
            return AnalysisRun.objects.get(
                content=review, configuration_hash=configuration_hash, is_current=True
            ), False
    return run, True


def analyze_content(
    content_id: int,
    provider: AIProvider,
    *,
    force: bool = False,
    max_retries: int = 1,
    batch_id: int | None = None,
) -> AnalysisRun:
    review = ReviewRecord.objects.select_related("product", "source").get(pk=content_id)
    run, should_execute = _create_run(review, provider, force=force, batch_id=batch_id)
    if not should_execute:
        return run
    feedback = ""
    try:
        for attempt in range(max_retries + 1):
            run.attempt_count = attempt + 1
            response = provider.analyze_review(_provider_input(review), prompt=_prompt(), validation_feedback=feedback)
            result: StructuredValidationResult | None
            try:
                result = validate_structured_payload(_decode(response.content), review.content)
            except (json.JSONDecodeError, ValueError) as exc:
                result = None
                feedback = f"INVALID_JSON:{exc}"
            else:
                feedback = "; ".join(result.errors)
            if result is not None and result.valid and result.payload is not None:
                _persist_success(
                    run, result.payload, response.latency_ms, response.prompt_tokens, response.completion_tokens
                )
                return run
        raise ValueError(feedback or "STRUCTURED_VALIDATION_FAILED")
    except AIProviderError as exc:
        _persist_failure(run, exc.code, exc.safe_message)
    except (ValueError, TypeError) as exc:
        _persist_failure(run, "STRUCTURED_VALIDATION_FAILED", str(exc)[:500])
    return run


def _persist_success(
    run: AnalysisRun,
    payload: StructuredAnalysisPayload,
    latency_ms: int,
    input_tokens: int | None,
    output_tokens: int | None,
) -> None:
    with transaction.atomic():
        analysis = StructuredAnalysis.objects.create(
            run=run,
            content=run.content,
            overall_sentiment=payload.overall_sentiment,
            language=payload.language,
            content_type=payload.content_type,
            relevance=payload.relevance,
            summary=payload.summary,
            model_mentions=payload.model_mentions,
            schema_valid=True,
            review_required=any(item.review_required or item.confidence < 0.65 for item in payload.aspects),
        )
        OpinionAspect.objects.bulk_create(
            [OpinionAspect(analysis=analysis, **item.model_dump()) for item in payload.aspects]
        )
        run.status = StructuredRunStatus.REVIEW_REQUIRED if analysis.review_required else StructuredRunStatus.SUCCEEDED
        run.latency_ms = latency_ms
        run.input_tokens = input_tokens
        run.output_tokens = output_tokens
        run.completed_at = timezone.now()
        run.error_code = ""
        run.error_message = ""
        run.save()


def _persist_failure(run: AnalysisRun, code: str, message: str) -> None:
    run.status = StructuredRunStatus.FAILED
    run.error_code = code
    run.error_message = message[:1000]
    run.completed_at = timezone.now()
    run.save()
