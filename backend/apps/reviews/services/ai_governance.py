"""P2 AI governance opinion: validated, auditable, never overrides rule decisions."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from django.utils import timezone

from ai.providers import AIProvider, AIProviderError
from ai.schemas.review_analysis import ReviewAnalysisInput
from apps.reviews.models import GovernanceAIReview, ReviewQuality

PROMPT_VERSION = "governance_review_v1"
PROMPT_PATH = Path(__file__).resolve().parents[4] / "prompts" / f"{PROMPT_VERSION}.md"
_FENCE = re.compile(r"^\s*```(?:json)?\s*(.*?)\s*```\s*$", re.I | re.S)


def validate_ai_governance_response(raw: str, original_content: str) -> dict:
    match = _FENCE.fullmatch(raw)
    payload = json.loads(match.group(1) if match else raw.strip())
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
    digest = hashlib.sha256(
        json.dumps(
            [review.title, review.content, quality.context_required, quality.eligible_for_ai,
             quality.exclusion_reason, quality.processor_version, provider.provider_name,
             provider.model, PROMPT_VERSION],
            ensure_ascii=False,
        ).encode("utf-8")
    ).hexdigest()
    if not force:
        existing = GovernanceAIReview.objects.filter(
            quality=quality, input_hash=digest,
            status__in=[GovernanceAIReview.Status.SUCCEEDED, GovernanceAIReview.Status.REVIEW_REQUIRED],
        ).order_by("-id").first()
        if existing:
            return existing
    item = GovernanceAIReview.objects.create(
        quality=quality, rule_eligible=quality.eligible_for_ai,
        input_hash=digest, provider=provider.provider_name, model_name=provider.model,
    )
    try:
        request = ReviewAnalysisInput(
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
        response = provider.analyze_review(request, prompt=PROMPT_PATH.read_text(encoding="utf-8"))
        payload = validate_ai_governance_response(response.content, review.content)
        item.ai_eligible = payload["eligible"]
        item.confidence = float(payload["confidence"])
        item.reason = payload["reason"]
        item.evidence = payload["evidence"]
        item.raw_response = payload
        item.prompt_tokens = response.prompt_tokens
        item.completion_tokens = response.completion_tokens
        # Conflicting, low-confidence or official content must never be silently accepted.
        conflict = item.ai_eligible != item.rule_eligible
        item.status = (
            GovernanceAIReview.Status.REVIEW_REQUIRED
            if conflict or item.confidence < 0.85 or quality.manual_override or quality.is_official_content
            else GovernanceAIReview.Status.SUCCEEDED
        )
    except AIProviderError as exc:
        item.status = GovernanceAIReview.Status.FAILED
        item.error_code = exc.code[:80]
    except (ValueError, TypeError, json.JSONDecodeError, OSError):
        item.status = GovernanceAIReview.Status.FAILED
        item.error_code = "INVALID_AI_OUTPUT"
    item.reviewed_at = timezone.now()
    item.save()
    return item
