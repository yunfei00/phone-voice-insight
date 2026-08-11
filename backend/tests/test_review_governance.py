# ruff: noqa: RUF001

import hashlib
import json
from datetime import datetime, timedelta

import pytest
from django.core.management import call_command
from django.utils import timezone
from rest_framework.test import APIClient

from apps.products.models import Product
from apps.reviews.models import (
    AnalysisCorpusItem,
    AuthorRole,
    ExclusionReason,
    RecordType,
    ReviewQuality,
    ReviewQualityRun,
    ReviewRecord,
)
from apps.reviews.services.experience_signal_detector import (
    classify_content_purpose,
    detect_product_experience_signal,
    is_non_phone_accessory_content,
)
from apps.reviews.services.governance_pipeline import (
    GovernanceProcessor,
    apply_manual_override,
    clear_manual_override,
    process_reviews,
)
from apps.reviews.services.low_information_detector import is_low_information
from apps.reviews.services.noise_detector import is_navigation_or_page_noise
from apps.reviews.services.text_normalizer import normalize_text
from apps.sources.models import DataSource, SourceTarget


def make_governance_review(
    *,
    source: DataSource,
    source_target: SourceTarget,
    product: Product,
    external_id: str | None,
    content: str,
    record_type: str = RecordType.THREAD,
    title: str = "荣耀Power2使用体验",
    parent_external_id: str = "",
    author_role: str = AuthorRole.USER,
    is_official: bool = False,
    published_at: datetime | None = None,
) -> ReviewRecord:
    actual_published_at = published_at if published_at is not None else timezone.now()
    return ReviewRecord.objects.create(
        source=source,
        source_target=source_target,
        product=product,
        external_id=external_id,
        parent_external_id=parent_external_id,
        record_type=record_type,
        title=title,
        content=content,
        author_role=author_role,
        is_official=is_official,
        content_hash=hashlib.sha256(f"{external_id}:{content}".encode()).hexdigest(),
        raw_data={},
        published_at=actual_published_at,
        collected_at=timezone.now(),
    )


def test_text_normalizer_preserves_semantics() -> None:
    value = "  荣耀\u200b Power2&nbsp; v1.2  \r\n\r\n\r\n  电量 80% 🔋  "

    assert normalize_text(value) == "荣耀 Power2 v1.2\n\n电量 80% 🔋"


@pytest.mark.parametrize(
    "value",
    (
        "支持",
        "支持下",
        "666",
        "顶",
        "哈哈",
        "路过",
        "感谢分享",
        "好",
        "好帖子。",
        "美拍",
        "100分",
        "可以",
        "厉害",
        "漂亮",
        "哦🙄",
    ),
)
def test_low_information_exact_terms(value: str) -> None:
    assert is_low_information(value)


@pytest.mark.parametrize("value", ("发热严重", "掉电快", "信号太差", "续航很好", "拍照一般", "太重了", "卡死了"))
def test_short_but_valuable_text_is_not_low_information(value: str) -> None:
    assert not is_low_information(value)


@pytest.mark.parametrize("value", ("感谢大佬分享", "求解答", "在哪里"))
def test_interaction_text_has_no_product_experience_signal(value: str) -> None:
    signal = detect_product_experience_signal(value)
    assert not signal.has_signal


@pytest.mark.parametrize(
    ("value", "aspect"),
    (
        ("续航不错", "BATTERY"),
        ("掉电快", "BATTERY"),
        ("信号太差", "SIGNAL"),
    ),
)
def test_short_experience_text_keeps_signal(value: str, aspect: str) -> None:
    signal = detect_product_experience_signal(value)
    assert signal.has_signal and aspect in signal.candidate_aspects


def test_short_reply_inherits_only_explicit_parent_experience() -> None:
    inherited = detect_product_experience_signal(
        "我也是",
        parent_text="升级后掉电特别快",
        allow_context_inheritance=True,
    )
    unrelated = detect_product_experience_signal(
        "我也是",
        parent_text="Power2壁纸分享",
        allow_context_inheritance=True,
    )
    assert inherited.has_signal and inherited.context_required
    assert inherited.candidate_aspects == ("BATTERY",)
    assert not unrelated.has_signal and not unrelated.context_required


def test_photo_share_is_not_camera_experience() -> None:
    shared = detect_product_experience_signal("相册里的AI作品不错")
    camera = detect_product_experience_signal("这手机拍照真的不错")
    assert not shared.has_signal
    assert classify_content_purpose("相册里的AI作品不错", has_experience_signal=False) == "PHOTO_SHARE"
    assert camera.has_signal and camera.candidate_aspects == ("CAMERA",)


def test_camera_location_is_build_quality_not_camera_experience() -> None:
    signal = detect_product_experience_signal("后盖照相机位置连续更换开裂")

    assert signal.has_signal
    assert signal.candidate_aspects == ("BUILD_QUALITY",)


def test_accessory_content_is_not_phone_experience() -> None:
    earphone = "荣耀亲选 AI通话耳机，独立屏幕并支持视频通话"
    watch = "这和通话手表相比还是差了一截"

    assert is_non_phone_accessory_content(earphone)
    assert is_non_phone_accessory_content(watch)
    assert not detect_product_experience_signal(earphone).has_signal
    assert not detect_product_experience_signal(watch).has_signal


def test_audio_usage_condition_is_not_audio_evaluation() -> None:
    condition = detect_product_experience_signal("基本上没开声音，或者开的很小")
    evaluation = detect_product_experience_signal("声音太小")

    assert not condition.has_signal
    assert evaluation.has_signal and evaluation.candidate_aspects == ("AUDIO_AND_CALL",)


def test_page_noise_is_conservative() -> None:
    assert is_navigation_or_page_noise("点赞")
    assert is_navigation_or_page_noise("点赞！")
    assert is_navigation_or_page_noise("点赞点赞！")
    assert is_navigation_or_page_noise("举报 | 回复 | 分享")
    assert is_navigation_or_page_noise("来自：荣耀俱乐部")
    assert not is_navigation_or_page_noise("点赞这个续航，确实很强")


@pytest.mark.django_db
def test_official_reply_is_excluded_but_moderator_reply_is_eligible(
    source: DataSource,
    source_target: SourceTarget,
    product: Product,
) -> None:
    thread = make_governance_review(
        source=source,
        source_target=source_target,
        product=product,
        external_id="honor_thread:1",
        content="更新后续航下降",
    )
    official = make_governance_review(
        source=source,
        source_target=source_target,
        product=product,
        external_id="honor_reply:official",
        content="您好，请升级最新版本",
        record_type=RecordType.OFFICIAL_REPLY,
        title="",
        parent_external_id=str(thread.external_id),
        author_role=AuthorRole.OFFICIAL,
        is_official=True,
    )
    moderator = make_governance_review(
        source=source,
        source_target=source_target,
        product=product,
        external_id="honor_reply:moderator",
        content="我也遇到了这个问题",
        record_type=RecordType.REPLY,
        title="",
        parent_external_id=str(thread.external_id),
        author_role=AuthorRole.MODERATOR,
    )

    result = process_reviews(ReviewRecord.objects.all(), reprocess=True)

    assert result.total == 3
    assert ReviewQuality.objects.get(review=official).exclusion_reason == ExclusionReason.OFFICIAL_CONTENT
    moderator_quality = ReviewQuality.objects.get(review=moderator)
    assert moderator_quality.is_product_related
    assert moderator_quality.eligible_for_ai


@pytest.mark.django_db
def test_reply_inherits_product_relevance_from_parent(
    source: DataSource,
    source_target: SourceTarget,
    product: Product,
) -> None:
    thread = make_governance_review(
        source=source,
        source_target=source_target,
        product=product,
        external_id="honor_thread:2",
        title="荣耀Power2续航问题",
        content="系统更新后续航下降",
    )
    reply = make_governance_review(
        source=source,
        source_target=source_target,
        product=product,
        external_id="honor_reply:2",
        title="",
        content="我也是，一晚上掉了20%",
        record_type=RecordType.REPLY,
        parent_external_id=str(thread.external_id),
    )

    decision = GovernanceProcessor().process(reply, persist=True, force=True)

    assert decision.is_product_related
    assert decision.eligible
    assert "帖子标题: 荣耀Power2续航问题" in AnalysisCorpusItem.objects.get(review=reply).context_text


@pytest.mark.django_db
def test_explicit_other_honor_model_is_not_product_related(
    source: DataSource,
    source_target: SourceTarget,
    product: Product,
) -> None:
    review = make_governance_review(
        source=source,
        source_target=source_target,
        product=product,
        external_id="honor_thread:other-model",
        title="荣耀V5使用问题",
        content="主板异常且相机打不开",
    )
    review.raw_data = {"device_source": "荣耀Power2", "topic_tags": ["荣耀Power2"]}
    review.save(update_fields=("raw_data", "updated_at"))

    decision = GovernanceProcessor().process(review, persist=True, force=True)

    assert not decision.eligible
    assert decision.exclusion_reason == ExclusionReason.PRODUCT_NOT_MATCHED


@pytest.mark.django_db
def test_high_confidence_commerce_copy_is_promotional(
    source: DataSource,
    source_target: SourceTarget,
    product: Product,
) -> None:
    review = make_governance_review(
        source=source,
        source_target=source_target,
        product=product,
        external_id="honor_thread:commerce-copy",
        title="荣耀Power2续航介绍",
        content="荣耀商城购机，赠价值598元礼包，享免息并返现",
    )

    decision = GovernanceProcessor().process(review, persist=True, force=True)

    assert not decision.eligible
    assert decision.exclusion_reason == ExclusionReason.PROMOTIONAL


@pytest.mark.django_db
def test_product_launch_spec_copy_is_promotional(
    source: DataSource,
    source_target: SourceTarget,
    product: Product,
) -> None:
    review = make_governance_review(
        source=source,
        source_target=source_target,
        product=product,
        external_id="honor_thread:spec-copy",
        title="荣耀Power2发布",
        content="荣耀Power2带来了千元机最大电池容量，10080毫安",
    )

    decision = GovernanceProcessor().process(review, persist=True, force=True)

    assert not decision.eligible
    assert decision.exclusion_reason == ExclusionReason.PROMOTIONAL


@pytest.mark.django_db
def test_ambiguous_photo_question_title_does_not_rescue_generic_body(
    source: DataSource,
    source_target: SourceTarget,
    product: Product,
) -> None:
    review = make_governance_review(
        source=source,
        source_target=source_target,
        product=product,
        external_id="honor_thread:title-context",
        title="荣耀Power2微信图片显示模糊怎么设置",
        content="求解答",
    )

    decision = GovernanceProcessor().process(review, persist=True, force=True)

    assert not decision.eligible
    assert decision.exclusion_reason == ExclusionReason.NO_PRODUCT_EXPERIENCE_SIGNAL


@pytest.mark.django_db
def test_generic_thread_title_does_not_rescue_low_information_body(
    source: DataSource,
    source_target: SourceTarget,
    product: Product,
) -> None:
    review = make_governance_review(
        source=source,
        source_target=source_target,
        product=product,
        external_id="honor_thread:generic-title",
        title="荣耀Power2使用体验",
        content="支持下",
    )

    decision = GovernanceProcessor().process(review, persist=True, force=True)

    assert not decision.eligible
    assert decision.exclusion_reason == ExclusionReason.SOCIAL_INTERACTION


@pytest.mark.django_db
def test_pipeline_is_idempotent_and_keeps_version_history(
    source: DataSource,
    source_target: SourceTarget,
    product: Product,
) -> None:
    make_governance_review(
        source=source,
        source_target=source_target,
        product=product,
        external_id="honor_thread:3",
        content="续航很好",
    )

    first = process_reviews(ReviewRecord.objects.all())
    second = process_reviews(ReviewRecord.objects.all())

    assert first.total == second.total == 1
    assert second.reused == 1
    assert ReviewQuality.objects.count() == 1
    assert ReviewQualityRun.objects.count() == 1
    assert AnalysisCorpusItem.objects.count() == 1


@pytest.mark.django_db
def test_manual_override_has_priority(
    source: DataSource,
    source_target: SourceTarget,
    product: Product,
) -> None:
    review = make_governance_review(
        source=source,
        source_target=source_target,
        product=product,
        external_id="honor_reply:low",
        content="支持",
        record_type=RecordType.REPLY,
    )
    GovernanceProcessor().process(review, persist=True, force=True)

    overridden = apply_manual_override(review.id, eligible=True, reason="人工确认包含有效上下文")
    rerun = GovernanceProcessor().process(review, persist=True, force=True)

    assert overridden.eligible and rerun.eligible
    assert ReviewQuality.objects.get(review=review).manual_override
    assert AnalysisCorpusItem.objects.get(review=review).eligible

    cleared = clear_manual_override(review.id)
    assert not cleared.eligible
    assert cleared.exclusion_reason == ExclusionReason.SOCIAL_INTERACTION


@pytest.mark.django_db
def test_duplicate_requires_missing_external_id_and_close_timestamp(
    source: DataSource,
    source_target: SourceTarget,
    product: Product,
) -> None:
    published_at = timezone.now()
    first = make_governance_review(
        source=source,
        source_target=source_target,
        product=product,
        external_id=None,
        content="荣耀Power2续航很好",
        published_at=published_at,
    )
    second = make_governance_review(
        source=source,
        source_target=source_target,
        product=product,
        external_id=None,
        content="荣耀Power2续航很好",
        published_at=published_at + timedelta(seconds=30),
    )
    distinct = make_governance_review(
        source=source,
        source_target=source_target,
        product=product,
        external_id="honor_thread:distinct",
        content="荣耀Power2续航很好",
        published_at=published_at + timedelta(seconds=30),
    )

    process_reviews(ReviewRecord.objects.all(), reprocess=True)

    assert not ReviewQuality.objects.get(review=first).is_duplicate
    assert ReviewQuality.objects.get(review=second).duplicate_of == first
    assert not ReviewQuality.objects.get(review=distinct).is_duplicate


@pytest.mark.django_db
def test_quality_api_filters_summarizes_and_applies_override(
    api_client: APIClient,
    source: DataSource,
    source_target: SourceTarget,
    product: Product,
) -> None:
    review = make_governance_review(
        source=source,
        source_target=source_target,
        product=product,
        external_id="honor_thread:api",
        content="支持",
    )
    GovernanceProcessor().process(review, persist=True, force=True)
    quality = ReviewQuality.objects.get(review=review)

    summary = api_client.get("/api/v1/review-quality/summary/")
    filtered = api_client.get("/api/v1/review-quality/", {"eligible": "false", "record_type": "THREAD"})
    override = api_client.post(
        f"/api/v1/review-quality/{quality.id}/override/",
        {"eligible": True, "reason": "人工复核"},
        format="json",
    )

    assert summary.status_code == 200
    assert summary.json()["total"] == 1
    assert summary.json()["exclusion_reasons"][ExclusionReason.SOCIAL_INTERACTION] == 1
    assert filtered.status_code == 200 and filtered.json()["count"] == 1
    assert override.status_code == 200 and override.json()["eligible_for_ai"] is True


@pytest.mark.django_db
def test_process_reviews_command_dry_run_does_not_write(
    source: DataSource,
    source_target: SourceTarget,
    product: Product,
    capsys: pytest.CaptureFixture[str],
) -> None:
    make_governance_review(
        source=source,
        source_target=source_target,
        product=product,
        external_id="honor_thread:command",
        content="荣耀Power2信号太差",
    )

    call_command("process_reviews", product="HONOR_POWER2", source="JD", limit=10, dry_run=True)
    output = json.loads(capsys.readouterr().out)

    assert output["total"] == 1
    assert output["dry_run"] is True
    assert ReviewQuality.objects.count() == 0
