from typing import Any

import pytest
from django.utils import timezone

from apps.accounts.models import AIProviderName, UserAIConfiguration, UserProfile, UserRole
from apps.reviews.models import ContentPurpose, GovernanceAIReview, ReviewQuality, ReviewRecord
from apps.reviews.services.automatic_pipeline import _govern_new_records, run_automatic_pipeline


def create_eligible_quality(product: Any, source: Any, source_target: Any) -> ReviewQuality:
    review = ReviewRecord.objects.create(
        source=source,
        source_target=source_target,
        product=product,
        external_id="automatic-pipeline-review",
        record_type="THREAD",
        content="夜间待机八小时掉电百分之二十",
        content_hash="automatic-pipeline-hash",
        collected_at=timezone.now(),
    )
    return ReviewQuality.objects.create(
        review=review,
        normalized_text=review.content,
        has_meaningful_text=True,
        is_product_related=True,
        has_product_experience_signal=True,
        content_purpose=ContentPurpose.PRODUCT_EXPERIENCE,
        eligible_for_ai=True,
        quality_score=0.95,
        processor_version="test-v1",
        processed_at=timezone.now(),
    )


@pytest.mark.django_db
def test_automatic_pipeline_is_disabled_by_default(product: Any) -> None:
    result = run_automatic_pipeline(product.id)
    assert result.status == "DISABLED"


@pytest.mark.django_db
def test_automatic_pipeline_queues_only_accepted_content(
    product: Any,
    source: Any,
    source_target: Any,
    django_user_model: Any,
    settings: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Existing deployments may have a legacy Django superuser without a UserProfile row.
    user = django_user_model.objects.create_superuser(username="automatic-admin", password="test-pass")
    UserAIConfiguration.objects.create(
        user=user,
        provider=AIProviderName.FAKE,
        model="fake-governance-v1",
        is_active=True,
    )
    quality = create_eligible_quality(product, source, source_target)
    settings.AI_AUTOMATION_ENABLED = True
    settings.AI_AUTOMATION_BATCH_SIZE = 10
    settings.AI_AUTOMATION_MAX_ATTEMPTS = 2
    settings.AI_AUTOMATION_DAILY_TOKEN_BUDGET = 1000
    settings.AI_AUTOMATION_REQUESTS_PER_MINUTE = 6
    settings.AI_ALLOW_FAKE_PROVIDER = True

    def accept(quality_id: int, provider: object, *, force: bool = False) -> GovernanceAIReview:
        del provider, force
        return GovernanceAIReview.objects.create(
            quality_id=quality_id,
            status=GovernanceAIReview.Status.ACCEPTED,
            rule_eligible=True,
            ai_eligible=True,
            confidence=0.95,
            reason="明确续航反馈",
            evidence="掉电百分之二十",
            input_hash="automatic-input-hash",
            prompt_tokens=10,
            completion_tokens=5,
            reviewed_at=timezone.now(),
            attempt_count=1,
        )

    queued: list[tuple[int, list[int]]] = []

    class Result:
        id = "structured-job"

    def enqueue(batch_id: int, content_ids: list[int], **kwargs: object) -> Result:
        del kwargs
        queued.append((batch_id, content_ids))
        return Result()

    monkeypatch.setattr("apps.reviews.tasks.review_quality_with_ai", accept)
    monkeypatch.setattr(
        "apps.reviews.services.automatic_pipeline.run_structured_analysis_batch_task.delay",
        enqueue,
    )

    result = run_automatic_pipeline(product.id, source.id)

    assert result.status == "STRUCTURED_QUEUED", result
    assert result.accepted == 1
    assert result.ai_items == 1
    assert result.prompt_tokens == 10
    assert result.completion_tokens == 5
    assert queued == [(result.structured_batch_id, [quality.review_id])]


@pytest.mark.django_db
def test_automatic_pipeline_stops_at_daily_budget(
    product: Any,
    django_user_model: Any,
    settings: Any,
) -> None:
    user = django_user_model.objects.create_user(username="budget-admin", password="test-pass")
    UserProfile.objects.create(user=user, role=UserRole.ADMIN)
    UserAIConfiguration.objects.create(user=user, provider=AIProviderName.FAKE, model="fake-v1")
    settings.AI_AUTOMATION_ENABLED = True
    settings.AI_AUTOMATION_DAILY_TOKEN_BUDGET = 0

    result = run_automatic_pipeline(product.id)

    assert result.status == "DAILY_BUDGET_EXCEEDED"


@pytest.mark.django_db
def test_automatic_governance_executes_with_celery_request_context(
    product: Any,
    source: Any,
    source_target: Any,
    django_user_model: Any,
) -> None:
    user = django_user_model.objects.create_superuser(username="governance-owner", password="test-pass")
    review = ReviewRecord.objects.create(
        source=source,
        source_target=source_target,
        product=product,
        external_id="new-automatic-review",
        record_type="THREAD",
        content="夜间待机八小时掉电百分之二十, 续航明显异常",
        content_hash="new-automatic-review-hash",
        collected_at=timezone.now(),
    )

    task = _govern_new_records(product, source.id, user.id)

    assert task is not None
    assert task.status == task.Status.SUCCESS
    assert ReviewQuality.objects.filter(review=review).exists()
