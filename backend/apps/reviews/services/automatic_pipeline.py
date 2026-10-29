"""Bounded, idempotent governance -> AI decision -> structured analysis pipeline."""

from __future__ import annotations

from dataclasses import asdict, dataclass

from django.conf import settings
from django.db import transaction
from django.db.models import Count, Q, Sum
from django.utils import timezone

from apps.accounts.models import UserAIConfiguration, UserRole
from apps.analysis.models import AnalysisBatch, AnalysisRun
from apps.analysis.tasks import run_structured_analysis_batch_task
from apps.products.models import Product
from apps.reviews.models import GovernanceAIBatch, GovernanceAIReview, GovernanceTask, ReviewQuality
from apps.reviews.services.governance_selection import governance_selection
from apps.reviews.tasks import process_governance_ai_batch, process_governance_batch
from apps.sources.models import DataSource


@dataclass(frozen=True)
class AutomaticPipelineResult:
    status: str
    product_id: int
    governance_task_id: int | None = None
    governed: int = 0
    ai_batch_id: int | None = None
    ai_items: int = 0
    accepted: int = 0
    rejected: int = 0
    uncertain: int = 0
    errors: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    structured_batch_id: int | None = None

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def _automation_configuration() -> UserAIConfiguration | None:
    configurations = (
        UserAIConfiguration.objects.select_related("user", "user__profile")
        .filter(is_active=True, user__is_active=True)
        .filter(Q(user__is_superuser=True) | Q(user__profile__role__in=(UserRole.ADMIN, UserRole.ANALYST)))
    )
    for configuration in configurations.order_by("user__profile__role", "user_id"):
        if configuration.is_configured:
            return configuration
    return None


def _tokens_used_today() -> int:
    start = timezone.localtime().replace(hour=0, minute=0, second=0, microsecond=0)
    governance = GovernanceAIReview.objects.filter(reviewed_at__gte=start).aggregate(
        prompt=Sum("prompt_tokens"), completion=Sum("completion_tokens")
    )
    structured = AnalysisRun.objects.filter(created_at__gte=start).aggregate(
        prompt=Sum("input_tokens"), completion=Sum("output_tokens")
    )
    return sum(
        int(value or 0)
        for value in (
            governance["prompt"],
            governance["completion"],
            structured["prompt"],
            structured["completion"],
        )
    )


def _govern_new_records(product: Product, source_id: int | None, owner_id: int) -> GovernanceTask | None:
    limit = int(settings.AI_AUTOMATION_BATCH_SIZE) * 10
    with transaction.atomic():
        Product.objects.select_for_update().get(pk=product.pk)
        active = GovernanceTask.objects.filter(
            product=product,
            trigger_type=GovernanceTask.TriggerType.AUTOMATIC,
            status__in=(GovernanceTask.Status.PENDING, GovernanceTask.Status.RUNNING),
        ).first()
        if active is not None:
            return active
        ids = governance_selection(product_id=product.id, source_id=source_id, limit=limit)
        if not ids:
            return None
        task = GovernanceTask.objects.create(
            product=product,
            source_id=source_id,
            requested_by_id=owner_id,
            trigger_type=GovernanceTask.TriggerType.AUTOMATIC,
            review_ids=ids,
            total=len(ids),
        )
    process_governance_batch.apply(args=(task.id,), throw=True)
    task.refresh_from_db()
    return task


def _ai_candidates(product_id: int, source_id: int | None) -> list[int]:
    terminal = (
        GovernanceAIReview.Status.ACCEPTED,
        GovernanceAIReview.Status.REJECTED,
        GovernanceAIReview.Status.UNCERTAIN,
        GovernanceAIReview.Status.SUCCEEDED,
        GovernanceAIReview.Status.REVIEW_REQUIRED,
    )
    queryset = ReviewQuality.objects.filter(
        review__product_id=product_id,
        eligible_for_ai=True,
    )
    if source_id is not None:
        queryset = queryset.filter(review__source_id=source_id)
    queryset = queryset.exclude(ai_reviews__status__in=terminal).annotate(
        error_attempts=Count("ai_reviews", filter=Q(ai_reviews__status=GovernanceAIReview.Status.ERROR))
    )
    queryset = queryset.filter(error_attempts__lt=settings.AI_AUTOMATION_MAX_ATTEMPTS)
    return list(queryset.order_by("review_id").values_list("id", flat=True)[: settings.AI_AUTOMATION_BATCH_SIZE])


def run_automatic_pipeline(product_id: int, source_id: int | None = None) -> AutomaticPipelineResult:
    if not settings.AI_AUTOMATION_ENABLED:
        return AutomaticPipelineResult(status="DISABLED", product_id=product_id)
    configuration = _automation_configuration()
    if configuration is None:
        return AutomaticPipelineResult(status="AI_NOT_CONFIGURED", product_id=product_id)
    budget = int(settings.AI_AUTOMATION_DAILY_TOKEN_BUDGET)
    used_tokens = _tokens_used_today()
    if settings.AI_AUTOMATION_TOKEN_LIMIT_MODE == "LIMITED" and (budget <= 0 or used_tokens >= budget):
        return AutomaticPipelineResult(status="DAILY_BUDGET_EXCEEDED", product_id=product_id)

    product = Product.objects.get(pk=product_id)
    governance_task = _govern_new_records(product, source_id, configuration.user_id)
    quality_ids = _ai_candidates(product.id, source_id)
    if not quality_ids:
        return AutomaticPipelineResult(
            status="NO_AI_CANDIDATES",
            product_id=product.id,
            governance_task_id=governance_task.id if governance_task else None,
            governed=governance_task.processed if governance_task else 0,
        )

    with transaction.atomic():
        Product.objects.select_for_update().get(pk=product.id)
        active_batch = GovernanceAIBatch.objects.filter(
            product=product,
            automatic=True,
            status__in=(GovernanceAIBatch.Status.PENDING, GovernanceAIBatch.Status.RUNNING),
        ).first()
        if active_batch is not None:
            return AutomaticPipelineResult(status="AI_BATCH_ACTIVE", product_id=product.id, ai_batch_id=active_batch.id)
        ai_batch = GovernanceAIBatch.objects.create(
            product=product,
            source_id=source_id,
            requested_by_id=configuration.user_id,
            automatic=True,
            quality_ids=quality_ids,
            total=len(quality_ids),
        )
    process_governance_ai_batch.apply(
        args=(ai_batch.id,),
        kwargs={"max_attempts": settings.AI_AUTOMATION_MAX_ATTEMPTS},
        throw=True,
    )
    ai_batch.refresh_from_db()

    accepted_content_ids: list[int] = []
    for quality in ReviewQuality.objects.filter(id__in=quality_ids).select_related("review"):
        latest = quality.ai_reviews.order_by("-id").first()
        if latest is not None and latest.status == GovernanceAIReview.Status.ACCEPTED:
            accepted_content_ids.append(quality.review_id)
    structured_batch: AnalysisBatch | None = None
    if accepted_content_ids:
        resolved_source_id = (
            source_id
            or ReviewQuality.objects.filter(id__in=quality_ids).values_list("review__source_id", flat=True).first()
        )
        if resolved_source_id is None:
            return AutomaticPipelineResult(
                status="SOURCE_NOT_FOUND",
                product_id=product_id,
                governance_task_id=governance_task.id if governance_task else None,
                ai_batch_id=ai_batch.id if ai_batch else None,
            )
        source = DataSource.objects.get(pk=resolved_source_id)
        remaining_tokens = (
            max(budget - _tokens_used_today(), 0)
            if settings.AI_AUTOMATION_TOKEN_LIMIT_MODE == "LIMITED"
            else None
        )
        structured_batch = AnalysisBatch.objects.create(
            created_by_id=configuration.user_id,
            product=product,
            source=source,
            corpus_version="automatic-v1",
            provider=configuration.provider,
            model_name=configuration.model,
            prompt_version="structured_analysis_v1",
            requested_count=len(accepted_content_ids),
            dry_run=False,
            max_concurrency=1,
            requests_per_minute=settings.AI_AUTOMATION_REQUESTS_PER_MINUTE,
            token_limit=remaining_tokens,
            cost_budget=None,
            status="PENDING",
        )
        run_structured_analysis_batch_task.delay(
            structured_batch.id,
            accepted_content_ids,
            max_retries=1,
        )

    return AutomaticPipelineResult(
        status="STRUCTURED_QUEUED" if structured_batch else "AI_COMPLETE",
        product_id=product.id,
        governance_task_id=governance_task.id if governance_task else None,
        governed=governance_task.processed if governance_task else 0,
        ai_batch_id=ai_batch.id,
        ai_items=ai_batch.processed,
        accepted=ai_batch.accepted,
        rejected=ai_batch.rejected,
        uncertain=ai_batch.uncertain,
        errors=ai_batch.failed,
        prompt_tokens=ai_batch.prompt_tokens,
        completion_tokens=ai_batch.completion_tokens,
        structured_batch_id=structured_batch.id if structured_batch else None,
    )
