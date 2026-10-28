"""V1 结构化分析执行服务；不在导入或启动时发起任何模型调用。"""

from __future__ import annotations

import hashlib
import json
import re
from functools import lru_cache
from pathlib import Path

from ai.providers import AIProvider, AIProviderError
from ai.schemas.review_analysis import ReviewAnalysisInput
from ai.schemas.structured_analysis import SCHEMA_VERSION, StructuredAnalysisPayload
from ai.taxonomy import TAXONOMY_VERSION, load_taxonomy
from ai.validation import StructuredValidationResult, validate_structured_payload
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.analysis.models import AnalysisRun, OpinionAspect, StructuredAnalysis, StructuredRunStatus
from apps.reviews.models import ReviewRecord

PROMPT_VERSION = "structured_analysis_v1"
_PROMPT_CANDIDATES = (
    Path(settings.BASE_DIR) / "prompts" / f"{PROMPT_VERSION}.md",
    Path(settings.BASE_DIR).parent / "prompts" / f"{PROMPT_VERSION}.md",
)
PROMPT_PATH = next((path for path in _PROMPT_CANDIDATES if path.is_file()), _PROMPT_CANDIDATES[0])
_FENCE = re.compile(r"^\s*```(?:json)?\s*(.*?)\s*```\s*$", re.DOTALL | re.IGNORECASE)


@lru_cache(maxsize=1)
def _prompt() -> str:
    base_prompt = PROMPT_PATH.read_text(encoding="utf-8")
    taxonomy = load_taxonomy()
    allowed_tags = {
        domain.tag_id: [child.tag_id for child in domain.children if child.enabled]
        for domain in taxonomy.domains
        if domain.enabled
    }
    schema = StructuredAnalysisPayload.model_json_schema()
    return (
        f"{base_prompt}\n\n"
        "## 本次必须遵循的完整 JSON Schema\n"
        f"{json.dumps(schema, ensure_ascii=False, separators=(',', ':'))}\n\n"
        "## 允许使用的一级标签与二级标签\n"
        f"{json.dumps(allowed_tags, ensure_ascii=False, separators=(',', ':'))}\n"
        "必须输出 Schema 顶层全部字段; aspects 中每个对象也必须输出全部必填字段。"
    )


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
    except OSError as exc:
        _persist_failure(run, "PROMPT_FILE_ERROR", str(exc)[:500])
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
