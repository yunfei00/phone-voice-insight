"""Contract tests for AI governance endpoints and batch execution."""

from typing import Any

import pytest
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.reviews.ai_views import GovernanceAIViewSet
from apps.reviews.models import GovernanceAIBatch
from apps.reviews.tasks import process_governance_ai_batch


@pytest.fixture
def admin_user(django_user_model: Any) -> Any:
    return django_user_model.objects.create_user(
        username="governance-admin", password="test-pass", is_staff=True, is_superuser=True
    )


@pytest.mark.django_db
def test_ai_start_rejects_invalid_limit(admin_user: Any) -> None:
    request = APIRequestFactory().post("/api/v1/governance-ai/start/", {"product_id": 1, "limit": 101}, format="json")
    force_authenticate(request, user=admin_user)
    response = GovernanceAIViewSet.as_view({"post": "start"})(request)
    assert response.status_code == 400


@pytest.mark.django_db
def test_ai_start_accepts_null_source_filter(admin_user: Any) -> None:
    request = APIRequestFactory().post(
        "/api/v1/governance-ai/start/",
        {"product_id": 999999, "source_id": None, "limit": 20},
        format="json",
    )
    force_authenticate(request, user=admin_user)
    response = GovernanceAIViewSet.as_view({"post": "start"})(request)
    assert response.status_code == 404
    assert response.data["detail"] == "产品不存在"


@pytest.mark.django_db
def test_ai_confirm_requires_pending_record(admin_user: Any) -> None:
    request = APIRequestFactory().post(
        "/api/v1/governance-ai/confirm/",
        {"review_id": 999999, "eligible": True, "reason": "人工检查后确认"},
        format="json",
    )
    force_authenticate(request, user=admin_user)
    response = GovernanceAIViewSet.as_view({"post": "confirm"})(request)
    assert response.status_code == 409


@pytest.mark.django_db
def test_ai_retry_rejects_unknown_batch(admin_user: Any) -> None:
    request = APIRequestFactory().post("/api/v1/governance-ai/retry-failed/", {"batch_id": 999999}, format="json")
    force_authenticate(request, user=admin_user)
    response = GovernanceAIViewSet.as_view({"post": "retry_failed"})(request)
    assert response.status_code == 404


@pytest.mark.django_db
def test_ai_history_starts_empty(admin_user: Any) -> None:
    request = APIRequestFactory().get("/api/v1/governance-ai/history/")
    force_authenticate(request, user=admin_user)
    response = GovernanceAIViewSet.as_view({"get": "history"})(request)
    assert response.status_code == 200
    assert response.data["results"] == []


def test_ai_batch_status_values() -> None:
    assert GovernanceAIBatch.Status.SUCCESS == "SUCCESS"
    assert GovernanceAIBatch.Status.PARTIAL == "PARTIAL"
    assert GovernanceAIBatch.Status.FAILED == "FAILED"


def test_ai_task_is_registered() -> None:
    assert process_governance_ai_batch.name == "process_governance_ai_batch"
