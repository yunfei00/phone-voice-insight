"""P2 AI governance opinion: validated, auditable, never overrides rule decisions."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from ai.providers import AIProvider, AIProviderError
from ai.schemas.review_analysis import ReviewAnalysisInput
from django.utils import timezone
from pydantic import ValidationError

from apps.reviews.models import GovernanceAIReview, ReviewQuality

PROMPT_VERSION = "governance_review_v1"
PROMPT_PATH = Path(__file__).resolve().parents[4] / "prompts" / f"{PROMPT_VERSION}.md"
_FENCE = re.compile(r"^\s*```(?:json)?\s*(.*?)\s*```\s*$", re.I | re.S)


def validate_ai_governance_response(raw: str, original_content: str) -> dict:
    match = _FENCE.fullmatch(raw)
    cleaned = match.group(1) if match else raw.strip()
    payload = json.loads(cleaned)
    if not isinstance(payload, dict) or set(payload) != {"eligible", "confidence", "reason", "evidence"}:
        raise ValueError("INVALID_FIELDS")
    if type(payload["eligible"]) is not bool:
        raise ValueError("INVALID_ELIGIBILITY")
    confidence = payload["confidence"]
    if type(confidence) not in (float, int) or not 0 <= confidence <= 1:
        raise ValueError("INVALID_CONFIDENCE")
    if not isinstance(payload["reason"], str) or not 1 <= len(payload["reason"]) <= 300:
        raise ValueError("INVALID_REASON")
    evidence = payload["evidence"]
    if not isinstance(evidence, str) or len(evidence) > 300 or (evidence and evidence not in original_content):
        raise ValueError("INVALID_EVIDENCE")
    return payload


def review_quality_with_ai(quality_id: int, provider: AIProvider, *, force: bool = False) -> GovernanceAIReview:
    quality = ReviewQuality.objects.select_related("review__product", "review__source").get(pk=quality_id)
    review = quality.review
    parent = None
    if quality.context_required and review.parent_external_id:
        parent = (
            type(review)
            .objects.filter(source_id=review.source_id, external_id=review.parent_external_id)
            .exclude(pk=review.pk)
            .order_by("-id")
            .first()
        )
    digest = hashlib.sha256(
        json.dumps(
            [
                review.title,
                review.content,
                quality.context_required,
                quality.eligible_for_ai,
                quality.exclusion_reason,
                quality.processor_version,
                provider.provider_name,
                provider.model,
                PROMPT_VERSION,
                parent.content if parent else "",
            ],
            ensure_ascii=False,
        ).encode("utf-8")
    ).hexdigest()
    if not force:
        existing = (
            GovernanceAIReview.objects.filter(
                quality=quality,
                input_hash=digest,
                status__in=[
                    GovernanceAIReview.Status.ACCEPTED,
                    GovernanceAIReview.Status.REJECTED,
                    GovernanceAIReview.Status.UNCERTAIN,
                    GovernanceAIReview.Status.SUCCEEDED,
                    GovernanceAIReview.Status.REVIEW_REQUIRED,
                ],
            )
            .order_by("-id")
            .first()
        )
        if existing:
            return existing
    previous_attempts = GovernanceAIReview.objects.filter(quality=quality, input_hash=digest).count()
    item = GovernanceAIReview.objects.create(
        quality=quality,
        rule_eligible=quality.eligible_for_ai,
        input_hash=digest,
        provider=provider.provider_name,
        model_name=provider.model,
        attempt_count=previous_attempts + 1,
    )
    try:
        if not review.content.strip():
            raise ValueError("EMPTY_REVIEW_CONTENT")
        request = ReviewAnalysisInput(
            review_id=str(review.id),
            product_model=review.product.name,
            content=review.content,
            title=review.title or None,
            source=review.source.code,
            record_type=review.record_type,
            author_role=review.author_role,
            content_purpose=quality.content_purpose,
            parent_review_id=str(parent.id) if parent else "",
            parent_content=parent.content[:2000] if parent else "",
            context_text=(parent.content[:2000] if parent and quality.context_required else ""),
            is_official=review.is_official,
            rating=float(review.rating) if review.rating is not None else None,
            software_version=review.software_version or None,
            published_at=review.published_at.isoformat() if review.published_at else None,
        )
        prompt = PROMPT_PATH.read_text(encoding="utf-8")
        response = provider.analyze_review(request, prompt=prompt)
        evidence_source = "\n".join(part for part in (review.content, parent.content if parent else "") if part)
        payload = validate_ai_governance_response(response.content, evidence_source)
        item.ai_eligible = payload["eligible"]
        item.confidence = float(payload["confidence"])
        item.reason = payload["reason"]
        item.evidence = payload["evidence"]
        item.raw_response = payload
        item.prompt_tokens = response.prompt_tokens
        item.completion_tokens = response.completion_tokens
        # High precision: only rule/AI agreement with sufficient confidence is accepted.
        conflict = item.ai_eligible != item.rule_eligible
        if quality.is_official_content or (not item.rule_eligible and not item.ai_eligible):
            item.status = GovernanceAIReview.Status.REJECTED
        elif conflict or item.confidence < 0.85 or quality.manual_override:
            item.status = GovernanceAIReview.Status.UNCERTAIN
        elif item.rule_eligible and item.ai_eligible:
            item.status = GovernanceAIReview.Status.ACCEPTED
        else:
            item.status = GovernanceAIReview.Status.REJECTED
    except AIProviderError as exc:
        item.status = GovernanceAIReview.Status.ERROR
        item.error_code = exc.code[:80]
    except (ValueError, TypeError, ValidationError, OSError) as exc:
        item.status = GovernanceAIReview.Status.ERROR
        if isinstance(exc, OSError):
            item.error_code = "PROMPT_FILE_ERROR"
        elif isinstance(exc, ValidationError):
            item.error_code = "INVALID_REVIEW_INPUT"
        elif isinstance(exc, json.JSONDecodeError):
            item.error_code = "AI_INVALID_JSON"
        elif str(exc) == "EMPTY_REVIEW_CONTENT":
            item.error_code = "EMPTY_REVIEW_CONTENT"
        elif str(exc).startswith("INVALID_"):
            item.error_code = str(exc)[:80]
        else:
            item.error_code = "INVALID_AI_OUTPUT"
    item.reviewed_at = timezone.now()
    item.save()
    return item
