# ruff: noqa: ARG001

from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import Mock, patch

import pytest
from django.contrib.auth import get_user_model
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import UserProfile, UserRole
from apps.analysis.models import AnalysisRun, OpinionAspect, StructuredAnalysis, StructuredRunStatus
from apps.products.models import Product
from apps.reports.models import AggregateReport, ReportType
from apps.reports.services import generate_report
from apps.reviews.models import (
    AuthorRole,
    GovernanceAIReview,
    RecordType,
    ReviewQuality,
    ReviewRecord,
)
from apps.sources.models import DataSource, SourceTarget, TargetType


def create_issue(
    *,
    product: Product,
    source: DataSource,
    target: SourceTarget,
    external_id: str,
    published_at: datetime | None = None,
    governance_status: str = GovernanceAIReview.Status.ACCEPTED,
    official: bool = False,
    topic_code: str = "NET.CELLULAR",
    aspect_code: str = "NET",
    severity: str = "HIGH",
) -> ReviewRecord:
    published_at = published_at or timezone.now()
    content = f"{external_id} 地下车库信号不稳定"
    review = ReviewRecord.objects.create(
        product=product,
        source=source,
        source_target=target,
        external_id=external_id,
        record_type=RecordType.OFFICIAL_REPLY if official else RecordType.REPLY,
        title="用户反馈",
        content=content,
        content_hash=(external_id * 64)[:64],
        author_role=AuthorRole.OFFICIAL if official else AuthorRole.USER,
        is_official=official,
        source_url=f"https://example.com/{external_id}",
        collected_at=published_at,
        published_at=published_at,
    )
    quality = ReviewQuality.objects.create(
        review=review,
        normalized_text=content,
        has_meaningful_text=True,
        is_product_related=True,
        has_product_experience_signal=True,
        is_official_content=official,
        eligible_for_ai=not official,
        quality_score=0.9,
        processor_version="dashboard-test",
        processed_at=published_at,
    )
    GovernanceAIReview.objects.create(
        quality=quality,
        status=governance_status,
        rule_eligible=not official,
        ai_eligible=governance_status == GovernanceAIReview.Status.ACCEPTED,
        confidence=0.95,
        reason="测试",
        evidence="信号不稳定",
        provider="fake",
        model_name="fake-v1",
        input_hash=(f"hash-{external_id}" * 10)[:64],
        reviewed_at=published_at,
    )
    run = AnalysisRun.objects.create(
        content=review,
        status=StructuredRunStatus.SUCCEEDED,
        provider="fake",
        model="fake-v1",
        input_hash=(f"input-{external_id}" * 10)[:64],
        configuration_hash=(f"config-{external_id}" * 10)[:64],
        started_at=published_at,
        completed_at=published_at,
    )
    analysis = StructuredAnalysis.objects.create(
        run=run,
        content=review,
        overall_sentiment="NEGATIVE",
        language="zh-CN",
        content_type="COMMUNITY_REPLY",
        relevance="RELEVANT",
        summary="用户反馈信号问题",
        schema_valid=True,
        review_required=False,
    )
    evidence = "信号不稳定"
    start = content.index(evidence)
    OpinionAspect.objects.create(
        analysis=analysis,
        business_domains=[aspect_code],
        aspect_code=aspect_code,
        topic_code=topic_code,
        sentiment="NEGATIVE",
        intent="COMPLAINT",
        issue_type="RELIABILITY",
        severity=severity,
        phenomenon=evidence,
        relation_type="SELF",
        evidence_text=evidence,
        evidence_start=start,
        evidence_end=start + len(evidence),
        confidence=0.95,
    )
    return review


@pytest.fixture
def second_product(product):  # type: ignore[no-untyped-def]
    return Product.objects.create(
        brand=product.brand,
        name="荣耀 Power",
        normalized_name="HONOR_POWER",
        series="Power",
        is_active=True,
    )


@pytest.fixture
def dashboard_data(product, second_product, source, source_target):  # type: ignore[no-untyped-def]
    second_target = SourceTarget.objects.create(
        source=source,
        product=second_product,
        name="第二入口",
        target_type=TargetType.COMMUNITY,
    )
    first = create_issue(product=product, source=source, target=source_target, external_id="a1")
    create_issue(
        product=product,
        source=source,
        target=source_target,
        external_id="uncertain",
        governance_status=GovernanceAIReview.Status.UNCERTAIN,
    )
    create_issue(product=product, source=source, target=source_target, external_id="official", official=True)
    create_issue(product=second_product, source=source, target=second_target, external_id="b1")
    return first


@pytest.mark.django_db
def test_overview_uses_real_accepted_distinct_feedback(api_client, dashboard_data):  # type: ignore[no-untyped-def]
    response = api_client.get("/api/v1/dashboard/overview/")
    assert response.status_code == 200
    assert response.data["raw_feedback"] == 4
    assert response.data["valid_feedback"] == 3
    assert response.data["ai_analyzed"] == 2
    assert response.data["explicit_issue_feedback"] == 2


@pytest.mark.django_db
def test_product_source_and_time_filters_are_isolated(api_client, dashboard_data, product):  # type: ignore[no-untyped-def]
    today = timezone.localdate().isoformat()
    response = api_client.get(
        "/api/v1/dashboard/overview/",
        {"product_id": product.id, "source_id": dashboard_data.source_id, "start_date": today, "end_date": today},
    )
    assert response.data["explicit_issue_feedback"] == 1
    assert response.data["raw_feedback"] == 3


@pytest.mark.django_db
def test_multiple_aspects_do_not_duplicate_total_feedback(api_client, dashboard_data):  # type: ignore[no-untyped-def]
    analysis = dashboard_data.structured_analyses.get()
    aspect = analysis.aspects.get()
    aspect.pk = None
    aspect.save()
    response = api_client.get("/api/v1/dashboard/overview/")
    assert response.data["explicit_issue_feedback"] == 2


@pytest.mark.django_db
def test_compared_product_negative_is_not_misattributed(api_client, product, source, source_target):  # type: ignore[no-untyped-def]
    review = create_issue(
        product=product,
        source=source,
        target=source_target,
        external_id="comparison-target",
    )
    OpinionAspect.objects.filter(analysis__content=review).update(
        target_product="荣耀 X70",
        compared_products=[product.name],
        relation_type="COMPARED_WITH",
    )

    overview_response = api_client.get("/api/v1/dashboard/overview/")
    category_response = api_client.get("/api/v1/dashboard/categories/")
    issue_response = api_client.get("/api/v1/dashboard/issues/")

    assert overview_response.data["ai_analyzed"] == 1
    assert overview_response.data["explicit_issue_feedback"] == 0
    assert category_response.data["results"] == []
    assert issue_response.data["count"] == 0


@pytest.mark.django_db
def test_issue_recent_count_uses_collected_time_fallback(api_client, product, source, source_target):  # type: ignore[no-untyped-def]
    review = create_issue(
        product=product,
        source=source,
        target=source_target,
        external_id="missing-published-at",
    )
    review.published_at = None
    review.save(update_fields=("published_at", "updated_at"))

    response = api_client.get("/api/v1/dashboard/issues/")

    assert response.status_code == 200
    assert response.data["results"][0]["recent_count"] == 1


@pytest.mark.django_db
def test_trends_and_categories_use_distinct_feedback(api_client, dashboard_data):  # type: ignore[no-untyped-def]
    trends_response = api_client.get("/api/v1/dashboard/trends/")
    categories_response = api_client.get("/api/v1/dashboard/categories/")
    assert trends_response.status_code == 200
    assert sum(row["explicit_issues"] for row in trends_response.data["results"]) == 2
    assert categories_response.data["results"][0]["feedback_count"] == 2
    assert categories_response.data["results"][0]["analyzed_denominator"] == 2


@pytest.mark.django_db
@override_settings(DASHBOARD_COMPARISON_MIN_SAMPLE=30)
def test_comparison_uses_analyzed_denominator_and_marks_small_samples(
    api_client: APIClient,
    dashboard_data: ReviewRecord,
    product: Product,
    second_product: Product,
) -> None:
    response = api_client.get(
        "/api/v1/dashboard/comparison/",
        {"left_product_id": product.id, "right_product_id": second_product.id},
    )
    assert response.status_code == 200
    assert response.data["left"]["negative_ratio"] == 1.0
    assert response.data["left"]["ratio_denominator"] == 1
    assert response.data["reliable"] is False
    assert "样本不足" in response.data["reliability_message"]


@pytest.mark.django_db
def test_issue_list_and_detail_trace_original_evidence(api_client, dashboard_data, product):  # type: ignore[no-untyped-def]
    listing = api_client.get("/api/v1/dashboard/issues/", {"product_id": product.id})
    assert listing.status_code == 200
    issue = listing.data["results"][0]
    detail = api_client.get(f"/api/v1/dashboard/issues/{issue['id']}/", {"product_id": product.id})
    assert detail.status_code == 200
    assert detail.data["evidence"][0]["analysis__content_id"] == dashboard_data.id
    assert detail.data["evidence"][0]["evidence_text"] in dashboard_data.content
    assert detail.data["evidence"][0]["analysis__content__source_url"] == dashboard_data.source_url


@pytest.mark.django_db
@override_settings(DASHBOARD_WATCH_MIN_COUNT=1, DASHBOARD_WATCH_GROWTH_PERCENT=50)
def test_watchlist_handles_zero_previous_period_as_new(api_client, dashboard_data):  # type: ignore[no-untyped-def]
    response = api_client.get("/api/v1/dashboard/overview/")
    assert response.data["watchlist"]
    assert response.data["watchlist"][0]["is_new"] is True
    assert response.data["watchlist"][0]["growth_rate"] is None


@pytest.mark.django_db
def test_empty_dashboard_is_explicit(api_client):  # type: ignore[no-untyped-def]
    response = api_client.get("/api/v1/dashboard/overview/")
    assert response.status_code == 200
    assert response.data["raw_feedback"] == 0
    assert response.data["ai_analyzed"] == 0
    assert response.data["latest_data_at"] is None


@pytest.mark.django_db
def test_report_generation_is_idempotent_and_has_period(api_client, dashboard_data, product):  # type: ignore[no-untyped-def]
    cutoff = timezone.now().replace(microsecond=0)
    first = generate_report(report_type=ReportType.DAILY, product=product, source=None, period_end=cutoff)
    second = generate_report(report_type=ReportType.DAILY, product=product, source=None, period_end=cutoff)
    assert first.id == second.id
    assert AggregateReport.objects.count() == 1
    assert first.period_end - first.period_start == timedelta(days=1)
    listing = api_client.get("/api/v1/dashboard/reports/")
    detail = api_client.get(f"/api/v1/dashboard/reports/{first.id}/")
    assert listing.data["count"] == 1
    assert detail.data["snapshot"]["top_issues"]


@pytest.mark.django_db
@override_settings(AI_AUTOMATION_ENABLED=False, AI_AUTOMATION_DAILY_TOKEN_BUDGET=1)
@patch("apps.reports.views.current_app")
@patch("apps.reports.views.get_redis_client")
def test_operations_reports_disabled_and_budget_exhaustion(redis_factory, celery_app, api_client, dashboard_data):  # type: ignore[no-untyped-def]
    redis_client = Mock()
    redis_client.ping.return_value = True
    redis_client.get.return_value = str(timezone.now().timestamp())
    redis_factory.return_value = redis_client
    celery_app.control.inspect.return_value.ping.return_value = {"worker": {"ok": "pong"}}
    run = AnalysisRun.objects.first()
    assert run is not None
    run.input_tokens = 2
    run.save(update_fields=("input_tokens", "updated_at"))
    response = api_client.get("/api/v1/dashboard/operations/")
    assert response.status_code == 200
    assert response.data["business_status"]["ai_automation"] == "disabled"
    assert response.data["ai"]["budget_exhausted"] is True
    assert response.data["role_scope"] == "full"


@pytest.mark.django_db
@patch("apps.reports.views.current_app")
@patch("apps.reports.views.get_redis_client")
def test_non_admin_operations_are_sanitized(redis_factory, celery_app):  # type: ignore[no-untyped-def]
    user = get_user_model().objects.create_user(username="viewer", password="password")
    UserProfile.objects.create(user=user, role=UserRole.VIEWER)
    client = APIClient()
    client.force_authenticate(user=user)
    redis_client = Mock()
    redis_client.ping.return_value = True
    redis_client.get.return_value = None
    redis_factory.return_value = redis_client
    celery_app.control.inspect.return_value.ping.return_value = {}
    response = client.get("/api/v1/dashboard/operations/")
    assert response.status_code == 200
    assert response.data["role_scope"] == "summary"
    assert "governance" not in response.data
    assert "api_key" not in str(response.data).lower()
    assert client.get("/api/v1/collection-tasks/").status_code == 403
    assert client.get("/api/v1/ai-configuration/").status_code == 403
    assert client.get("/api/v1/structured-batches/").status_code == 403


@pytest.mark.django_db
def test_anonymous_dashboard_access_is_denied() -> None:
    response = APIClient().get("/api/v1/dashboard/overview/")
    assert response.status_code in (401, 403)
