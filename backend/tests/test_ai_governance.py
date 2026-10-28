import json
from typing import Any

import pytest
from ai.providers.base import AIProviderError, AIProviderResponse
from django.utils import timezone

from apps.reviews.models import ContentPurpose, GovernanceAIReview, RecordType, ReviewQuality, ReviewRecord
from apps.reviews.services.ai_governance import review_quality_with_ai, validate_ai_governance_response


class GovernanceProvider:
    provider_name = "fake-governance"
    model = "fake-governance-v1"

    def __init__(self, payload: dict[str, object] | None = None, *, error: bool = False) -> None:
        self.payload = payload or {}
        self.error = error

    def analyze_review(self, request: object, *, prompt: str, validation_feedback: str = "") -> AIProviderResponse:
        del request, prompt, validation_feedback
        if self.error:
            raise AIProviderError("AI_TIMEOUT", "模拟超时", retriable=True)
        return AIProviderResponse(
            provider=self.provider_name,
            model=self.model,
            content=json.dumps(self.payload, ensure_ascii=False),
            latency_ms=1,
            prompt_tokens=12,
            completion_tokens=8,
        )


def create_quality(
    product: Any,
    source: Any,
    source_target: Any,
    *,
    content: str,
    eligible: bool,
    external_id: str,
    parent_external_id: str = "",
    context_required: bool = False,
) -> ReviewQuality:
    review = ReviewRecord.objects.create(
        source=source,
        source_target=source_target,
        product=product,
        external_id=external_id,
        parent_external_id=parent_external_id,
        record_type=RecordType.REPLY if parent_external_id else RecordType.THREAD,
        content=content,
        content_hash=f"hash-{external_id}",
        collected_at=timezone.now(),
    )
    return ReviewQuality.objects.create(
        review=review,
        normalized_text=content,
        has_meaningful_text=True,
        is_product_related=True,
        has_product_experience_signal=eligible,
        context_required=context_required,
        content_purpose=ContentPurpose.PRODUCT_EXPERIENCE,
        eligible_for_ai=eligible,
        quality_score=0.9,
        processor_version="test-v1",
        processed_at=timezone.now(),
    )


def test_valid_ai_governance_response() -> None:
    payload = validate_ai_governance_response(
        '{"eligible":true,"confidence":0.92,"reason":"有明确耗电反馈","evidence":"耗电很快"}',
        "升级后耗电很快",
    )
    assert payload["eligible"] is True
    assert payload["evidence"] == "耗电很快"


@pytest.mark.parametrize(
    "response",
    [
        '{"eligible":"true","confidence":0.9,"reason":"测试","evidence":""}',
        '{"eligible":true,"confidence":1.2,"reason":"测试","evidence":""}',
        '{"eligible":true,"confidence":0.8,"reason":"测试","evidence":"编造证据"}',
        '{"eligible":true,"confidence":0.8,"reason":"","evidence":""}',
        '{"eligible":true,"confidence":0.8,"reason":"测试","evidence":"","extra":"x"}',
        "not json",
    ],
)
def test_invalid_ai_governance_response_is_rejected(response: str) -> None:
    with pytest.raises((ValueError, TypeError)):
        validate_ai_governance_response(response, "升级后耗电很快")


def test_governance_prompt_exists() -> None:
    from apps.reviews.services.ai_governance import _PROMPT_CANDIDATES, PROMPT_PATH

    assert PROMPT_PATH.is_file(), f"Governance AI prompt missing: {PROMPT_PATH}"
    assert PROMPT_PATH in _PROMPT_CANDIDATES
    assert "eligible" in PROMPT_PATH.read_text(encoding="utf-8")


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("eligible", "confidence", "rule_eligible", "expected"),
    [
        (True, 0.95, True, GovernanceAIReview.Status.ACCEPTED),
        (False, 0.95, False, GovernanceAIReview.Status.REJECTED),
        (True, 0.70, True, GovernanceAIReview.Status.UNCERTAIN),
    ],
)
def test_ai_governance_automatic_decisions(
    product: Any,
    source: Any,
    source_target: Any,
    eligible: bool,
    confidence: float,
    rule_eligible: bool,
    expected: str,
) -> None:
    quality = create_quality(
        product,
        source,
        source_target,
        content="待机耗电很快",
        eligible=rule_eligible,
        external_id=f"decision-{expected}",
    )
    provider = GovernanceProvider(
        {
            "eligible": eligible,
            "confidence": confidence,
            "reason": "自动判断测试",
            "evidence": "耗电很快",
        }
    )
    result = review_quality_with_ai(quality.id, provider)  # type: ignore[arg-type]
    assert result.status == expected
    assert result.prompt_tokens == 12
    assert result.completion_tokens == 8


@pytest.mark.django_db
def test_ai_governance_error_is_not_rejected(product: Any, source: Any, source_target: Any) -> None:
    quality = create_quality(
        product,
        source,
        source_target,
        content="充电时发热",
        eligible=True,
        external_id="decision-error",
    )
    result = review_quality_with_ai(quality.id, GovernanceProvider(error=True))  # type: ignore[arg-type]
    assert result.status == GovernanceAIReview.Status.ERROR
    assert result.error_code == "AI_TIMEOUT"


@pytest.mark.django_db
def test_short_reply_can_use_parent_evidence(product: Any, source: Any, source_target: Any) -> None:
    create_quality(
        product,
        source,
        source_target,
        content="荣耀 Power 充电时发热明显",
        eligible=True,
        external_id="parent-thread",
    )
    quality = create_quality(
        product,
        source,
        source_target,
        content="我的也是",
        eligible=True,
        external_id="short-reply",
        parent_external_id="parent-thread",
        context_required=True,
    )
    provider = GovernanceProvider(
        {
            "eligible": True,
            "confidence": 0.93,
            "reason": "结合父帖可确认发热反馈",
            "evidence": "充电时发热明显",
        }
    )
    result = review_quality_with_ai(quality.id, provider)  # type: ignore[arg-type]
    assert result.status == GovernanceAIReview.Status.ACCEPTED
    assert result.evidence == "充电时发热明显"
