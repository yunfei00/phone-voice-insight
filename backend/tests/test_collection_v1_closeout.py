from __future__ import annotations

from datetime import datetime
from io import StringIO
from zoneinfo import ZoneInfo

import pytest
from collectors.base import CollectorError
from collectors.honor_club.client import HonorHttpResponse
from collectors.honor_club.normalizer import is_product_related
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import UserProfile, UserRole
from apps.collection.models import CollectionStatus, CollectionTargetState, CollectionTargetStatus, CollectionTask
from apps.collection.services.smart_collection import SmartCollectionRejected, start_smart_collection
from apps.products.models import Product
from apps.reviews.models import ReviewRecord
from apps.sources.models import SourceTarget, TargetValidationStatus
from apps.sources.services.target_validation import TargetValidationResult, target_url_hash, validate_source_target


@pytest.mark.django_db
def test_honor_power_initialization_is_idempotent() -> None:
    call_command("ensure_honor_power_products")
    call_command("ensure_honor_power_products")

    assert Product.objects.filter(normalized_name__in=("HONOR_POWER", "HONOR_POWER2")).count() == 2
    power = Product.objects.get(normalized_name="HONOR_POWER")
    power2 = Product.objects.get(normalized_name="HONOR_POWER2")
    assert power.source_targets.get(source__code="HONOR_CLUB").target_url.endswith("threadtopic-521-1.html")
    assert power2.source_targets.get(source__code="HONOR_CLUB").target_url.endswith("threadtopic-595-1.html")


def test_power_and_power2_matching_do_not_cross() -> None:
    assert not is_product_related(
        title="荣耀 Power2 新机体验",
        content="",
        topic_tags=["#荣耀Power2#"],
        aliases=["荣耀 Power", "Power"],
        excluded_aliases=["荣耀 Power2", "Power2"],
    )


def test_entry_dns_rejects_private_address(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "apps.sources.services.target_validation.socket.getaddrinfo",
        lambda *_args, **_kwargs: [(2, 1, 6, "", ("127.0.0.1", 443))],
    )
    from apps.sources.services.target_validation import _public_addresses

    with pytest.raises(CollectorError, match="非公网地址"):
        _public_addresses("club.honor.com")
    assert is_product_related(
        title="荣耀 Power2 新机体验",
        content="",
        topic_tags=["#荣耀Power2#"],
        aliases=["荣耀 Power2", "Power2"],
        excluded_aliases=["荣耀 Power", "Power"],
    )


@pytest.mark.django_db
def test_entry_validation_accepts_correct_topic_and_rejects_cross_product(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    call_command("ensure_honor_power_products")
    power = Product.objects.get(normalized_name="HONOR_POWER")
    target = power.source_targets.get(source__code="HONOR_CLUB")
    html = """
      <html><title>荣耀俱乐部</title><body>
      <div class='section-name'>#荣耀Power#</div><div id='threadlist'>
      <div class='gm-hlink'><a href='/cn/thread-12345-1-1.html' title='荣耀Power体验'>荣耀Power体验</a></div>
      </div></body></html>
    """
    monkeypatch.setattr("apps.sources.services.target_validation._public_addresses", lambda _host: ["1.1.1.1"])
    monkeypatch.setattr(
        "apps.sources.services.target_validation.HonorClubClient.get_html",
        lambda *_args, **_kwargs: HonorHttpResponse(html, target.target_url, 200, 10),
    )
    assert validate_source_target(target).valid is True
    target.refresh_from_db()
    assert target.validation_status == TargetValidationStatus.VALID

    wrong = html.replace("#荣耀Power#", "#荣耀Power2#")
    monkeypatch.setattr(
        "apps.sources.services.target_validation.HonorClubClient.get_html",
        lambda *_args, **_kwargs: HonorHttpResponse(wrong, target.target_url, 200, 10),
    )
    result = validate_source_target(target)
    assert result == TargetValidationResult(False, "PRODUCT_MISMATCH", result.message, result.report)


@pytest.mark.django_db
def test_entry_url_change_invalidates_validation_and_full_baseline(
    api_client: APIClient,
    source_target: SourceTarget,
) -> None:
    source_target.validation_status = TargetValidationStatus.VALID
    source_target.validated_url_hash = target_url_hash(source_target.target_url)
    source_target.save(update_fields=("validation_status", "validated_url_hash"))
    state = CollectionTargetState.objects.get(source_target=source_target)
    state.full_verified = True
    state.status = CollectionTargetStatus.READY
    state.save()

    response = api_client.patch(
        f"/api/v1/source-targets/{source_target.id}/",
        {"target_url": "https://club.honor.com/cn/threadtopic-521-1.html"},
        format="json",
    )

    assert response.status_code == 200
    source_target.refresh_from_db()
    state.refresh_from_db()
    assert source_target.validation_status == TargetValidationStatus.UNVERIFIED
    assert state.full_verified is False


def _mark_valid(target: SourceTarget) -> None:
    target.target_url = "https://club.honor.com/cn/threadtopic-595-1.html"
    target.validation_status = TargetValidationStatus.VALID
    target.validated_url_hash = target_url_hash(target.target_url)
    target.save(update_fields=("target_url", "validation_status", "validated_url_hash"))


@pytest.mark.django_db
def test_smart_collection_first_full_then_incremental(
    source_target: SourceTarget,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _mark_valid(source_target)
    monkeypatch.setattr(
        "apps.collection.tasks.run_collection_task.delay", lambda _task_id: type("R", (), {"id": "x"})()
    )
    first = start_smart_collection(source_target.id)
    assert first.task.task_type == "FULL"
    first.task.status = CollectionStatus.SUCCESS
    first.task.save(update_fields=("status",))
    state = CollectionTargetState.objects.get(source_target=source_target)
    state.active_task = None
    state.full_verified = True
    state.status = CollectionTargetStatus.READY
    state.save()

    second = start_smart_collection(source_target.id)
    assert second.task.task_type == "INCREMENTAL"


@pytest.mark.django_db
def test_smart_collection_submit_failure_is_not_left_pending(
    source_target: SourceTarget,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _mark_valid(source_target)

    def fail(_task_id: int) -> None:
        raise RuntimeError("broker down")

    monkeypatch.setattr("apps.collection.tasks.run_collection_task.delay", fail)
    with pytest.raises(SmartCollectionRejected, match="Celery"):
        start_smart_collection(source_target.id)
    task = CollectionTask.objects.get(source_target=source_target)
    assert task.status == CollectionStatus.FAILED
    assert CollectionTargetState.objects.get(source_target=source_target).active_task_id is None


@pytest.mark.django_db
def test_cleanup_is_admin_only_isolated_and_resets_baseline(
    api_client: APIClient,
    source_target: SourceTarget,
    product: Product,
) -> None:
    other = SourceTarget.objects.create(
        source=source_target.source,
        product=product,
        name="另一个入口",
        target_type=source_target.target_type,
    )
    own = ReviewRecord.objects.create(
        source=source_target.source,
        source_target=source_target,
        product=product,
        external_id="own",
        record_type="THREAD",
        title="本入口",
        content="内容",
        content_hash="a" * 64,
        collected_at=timezone.now(),
    )
    foreign = ReviewRecord.objects.create(
        source=source_target.source,
        source_target=other,
        product=product,
        external_id="foreign",
        record_type="THREAD",
        title="其他入口",
        content="内容",
        content_hash="b" * 64,
        collected_at=timezone.now(),
    )
    preview = api_client.get(f"/api/v1/source-targets/{source_target.id}/cleanup-preview/")
    assert preview.status_code == 200
    assert preview.json()["thread_count"] == 1
    denied = api_client.post(
        f"/api/v1/source-targets/{source_target.id}/cleanup/", {"confirmation": "wrong"}, format="json"
    )
    assert denied.status_code == 400
    response = api_client.post(
        f"/api/v1/source-targets/{source_target.id}/cleanup/",
        {"confirmation": f"DELETE {source_target.id}"},
        format="json",
    )
    assert response.status_code == 200
    assert not ReviewRecord.objects.filter(pk=own.pk).exists()
    assert ReviewRecord.objects.filter(pk=foreign.pk).exists()
    assert source_target.collection_state.full_verified is False

    viewer = get_user_model().objects.create_user(username="viewer", password="password")
    UserProfile.objects.create(user=viewer, role=UserRole.VIEWER)
    viewer_client = APIClient()
    viewer_client.force_authenticate(viewer)
    assert viewer_client.get(f"/api/v1/source-targets/{other.id}/cleanup-preview/").status_code == 403


@pytest.mark.django_db
def test_backfill_only_uses_reliable_raw_metadata(source_target: SourceTarget, product: Product) -> None:
    review = ReviewRecord.objects.create(
        source=source_target.source,
        source_target=source_target,
        product=product,
        external_id="backfill",
        record_type="REPLY",
        content="内容",
        content_hash="c" * 64,
        raw_data={"published_at_raw": "2026-10-27 15:30", "public_region": "陕西"},
        collected_at=timezone.now(),
    )
    output = StringIO()
    call_command("backfill_review_metadata", dry_run=True, stdout=output)
    review.refresh_from_db()
    assert review.published_at is None
    call_command("backfill_review_metadata", apply=True, stdout=output)
    review.refresh_from_db()
    assert review.published_at == datetime(2026, 10, 27, 15, 30, tzinfo=ZoneInfo("Asia/Shanghai"))
    assert review.source_region == "陕西"
    assert review.region_evidence == "public_ip_region"
