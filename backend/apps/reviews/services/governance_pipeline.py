"""Deterministic and idempotent review governance pipeline."""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any

from django.db import transaction
from django.db.models import Q, QuerySet
from django.utils import timezone

from apps.reviews.models import (
    AnalysisCorpusItem,
    AuthorRole,
    ContentPurpose,
    ExclusionReason,
    RecordType,
    ReviewQuality,
    ReviewQualityRun,
    ReviewRecord,
)
from apps.reviews.services.constants import CORPUS_VERSION, GOVERNANCE_PROCESSOR_VERSION
from apps.reviews.services.context_builder import build_analysis_context, find_parent_review
from apps.reviews.services.experience_signal_detector import (
    classify_content_purpose,
    detect_product_experience_signal,
)
from apps.reviews.services.low_information_detector import is_low_information
from apps.reviews.services.metadata_reply_detector import detect_metadata_reply
from apps.reviews.services.noise_detector import is_navigation_or_page_noise
from apps.reviews.services.platform_boilerplate_cleaner import clean_platform_boilerplate
from apps.reviews.services.product_relevance import is_product_related
from apps.reviews.services.promotional_detector import is_promotional_content
from apps.reviews.services.text_normalizer import normalize_text

_GENERIC_THREAD_TITLES = frozenset({"荣耀power2使用体验", "荣耀power2", "使用体验", "分享"})


@dataclass(frozen=True)
class GovernanceDecision:
    review_id: int
    record_type: str
    content_preview: str
    eligible: bool
    exclusion_reason: str
    quality_score: float
    is_official: bool
    is_low_information: bool
    is_promotional: bool
    is_noise: bool
    is_product_related: bool
    has_product_experience_signal: bool
    context_required: bool
    content_purpose: str
    candidate_aspects: tuple[str, ...]
    is_duplicate: bool
    is_empty: bool
    reused: bool = False


@dataclass(frozen=True)
class GovernanceBatchResult:
    total: int
    eligible: int
    excluded: int
    official: int
    low_information: int
    promotional: int
    noise: int
    product_not_matched: int
    duplicate: int
    empty: int
    reused: int
    exclusion_reasons: dict[str, int]
    decisions: tuple[GovernanceDecision, ...]

    def as_dict(self, *, include_decisions: bool = False) -> dict[str, Any]:
        result = asdict(self)
        if not include_decisions:
            result.pop("decisions", None)
        return result


def _is_official(review: ReviewRecord) -> bool:
    if review.author_role in {AuthorRole.MODERATOR, AuthorRole.EXPERT}:
        return review.record_type == RecordType.OFFICIAL_REPLY
    return (
        review.record_type == RecordType.OFFICIAL_REPLY
        or review.author_role == AuthorRole.OFFICIAL
        or review.is_official
    )


def _automatic_exclusion_reason(
    *,
    is_empty: bool,
    invalid_encoding: bool,
    official: bool,
    product_related: bool,
    noise: bool,
    promotional: bool,
    low_information: bool,
    duplicate: bool,
    supported_record_type: bool,
    has_product_experience_signal: bool,
    content_purpose: str,
) -> str:
    if is_empty:
        return ExclusionReason.EMPTY_CONTENT
    if invalid_encoding:
        return ExclusionReason.INVALID_ENCODING
    if official:
        return ExclusionReason.OFFICIAL_CONTENT
    if not product_related:
        return ExclusionReason.PRODUCT_NOT_MATCHED
    if noise:
        return ExclusionReason.PAGE_NOISE
    if promotional:
        return ExclusionReason.PROMOTIONAL
    if duplicate:
        return ExclusionReason.DUPLICATE
    if not supported_record_type:
        return ExclusionReason.OTHER
    if content_purpose == ContentPurpose.METADATA_REPLY:
        return ExclusionReason.METADATA_REPLY
    if not has_product_experience_signal:
        if content_purpose == ContentPurpose.SOCIAL_INTERACTION:
            return ExclusionReason.SOCIAL_INTERACTION
        if content_purpose == ContentPurpose.RESOURCE_SHARE:
            return ExclusionReason.RESOURCE_SHARE
        if content_purpose == ContentPurpose.PHOTO_SHARE:
            return ExclusionReason.PHOTO_SHARE
        return ExclusionReason.NO_PRODUCT_EXPERIENCE_SIGNAL
    if low_information:
        return ExclusionReason.LOW_INFORMATION
    return ExclusionReason.NONE


def _quality_score(
    *,
    is_empty: bool,
    invalid_encoding: bool,
    official: bool,
    product_related: bool,
    noise: bool,
    promotional: bool,
    low_information: bool,
    duplicate: bool,
    published_at: datetime | None,
    context_sufficient: bool,
    has_product_experience_signal: bool,
) -> float:
    score = 1.0
    if is_empty or invalid_encoding or official or not product_related or noise or duplicate:
        score -= 1.0
    if promotional:
        score -= 0.8
    if low_information:
        score -= 0.6
    if not has_product_experience_signal:
        score -= 0.7
    if published_at is None:
        score -= 0.05
    if not context_sufficient:
        score -= 0.1
    return round(min(max(score, 0.0), 1.0), 2)


def _decision_from_quality(quality: ReviewQuality, *, reused: bool) -> GovernanceDecision:
    review = quality.review
    return GovernanceDecision(
        review_id=review.id,
        record_type=review.record_type,
        content_preview=quality.normalized_text[:100],
        eligible=quality.eligible_for_ai,
        exclusion_reason=quality.exclusion_reason,
        quality_score=quality.quality_score,
        is_official=quality.is_official_content,
        is_low_information=quality.is_low_information,
        is_promotional=quality.is_promotional,
        is_noise=quality.is_navigation_or_page_noise,
        is_product_related=quality.is_product_related,
        has_product_experience_signal=quality.has_product_experience_signal,
        context_required=quality.context_required,
        content_purpose=quality.content_purpose,
        candidate_aspects=tuple(quality.flags_json.get("candidate_aspects", ())),
        is_duplicate=quality.is_duplicate,
        is_empty=not bool(quality.normalized_text),
        reused=reused,
    )


class GovernanceProcessor:
    """Process reviews in stable ID order while tracking duplicate candidates."""

    def __init__(self) -> None:
        self._seen_without_external_id: dict[tuple[int, str, str], list[tuple[int, datetime | None]]] = {}

    def _remember(self, review: ReviewRecord, normalized_text: str) -> None:
        if review.external_id or not normalized_text:
            return
        key = (review.source_id, review.record_type, normalized_text)
        self._seen_without_external_id.setdefault(key, []).append((review.id, review.published_at))

    def _find_duplicate(self, review: ReviewRecord, normalized_text: str) -> ReviewRecord | None:
        if review.external_id:
            return (
                ReviewRecord.objects.filter(
                    source_id=review.source_id,
                    record_type=review.record_type,
                    external_id=review.external_id,
                    id__lt=review.id,
                )
                .order_by("id")
                .first()
            )
        if not normalized_text or review.published_at is None:
            return None
        key = (review.source_id, review.record_type, normalized_text)
        for review_id, published_at in self._seen_without_external_id.get(key, []):
            if published_at is not None and abs((review.published_at - published_at).total_seconds()) <= 300:
                return ReviewRecord.objects.filter(pk=review_id).first()
        candidates = ReviewQuality.objects.filter(
            review__source_id=review.source_id,
            review__record_type=review.record_type,
            review__id__lt=review.id,
            normalized_text=normalized_text,
        ).filter(Q(review__external_id__isnull=True) | Q(review__external_id=""))
        candidates = candidates.select_related("review")
        for candidate in candidates.order_by("review_id"):
            published_at = candidate.review.published_at
            if published_at is not None and abs((review.published_at - published_at).total_seconds()) <= 300:
                return candidate.review
        return None

    def process(self, review: ReviewRecord, *, persist: bool = True, force: bool = False) -> GovernanceDecision:
        existing = ReviewQuality.objects.filter(review=review).select_related("review").first()
        if (
            persist
            and existing is not None
            and existing.processor_version == GOVERNANCE_PROCESSOR_VERSION
            and not force
        ):
            self._remember(review, existing.normalized_text)
            return _decision_from_quality(existing, reused=True)

        cleaning_result = clean_platform_boilerplate(review.content)
        normalized_text = cleaning_result.text
        parent = find_parent_review(review)
        context = build_analysis_context(review, parent=parent)
        invalid_encoding = "\ufffd" in normalized_text
        is_empty = not bool(normalized_text)
        official = _is_official(review)
        noise = is_navigation_or_page_noise(normalized_text)
        low_information = is_low_information(normalized_text) if not noise else False
        if low_information and review.record_type == RecordType.THREAD:
            normalized_title = normalize_text(review.title)
            compact_title = "".join(normalized_title.split()).casefold()
            title_is_meaningful = (
                len(compact_title) >= 6
                and compact_title not in _GENERIC_THREAD_TITLES
                and compact_title != "".join(normalized_text.split()).casefold()
                and not is_low_information(normalized_title)
                and not is_navigation_or_page_noise(normalized_title)
            )
            low_information = not title_is_meaningful
        promotional = is_promotional_content(
            title=review.title,
            content=normalized_text,
            is_official=official,
        )
        product_related = is_product_related(review, parent=parent)
        signal_text = normalized_text
        parent_signal_text = (
            f"{parent.title}\n{clean_platform_boilerplate(parent.content).text}" if parent is not None else ""
        )
        parent_allows_inheritance = bool(
            parent is not None
            and not _is_official(parent)
            and not is_promotional_content(
                title=parent.title,
                content=normalize_text(parent.content),
                is_official=False,
            )
        )
        metadata_reply = detect_metadata_reply(signal_text) if review.record_type == RecordType.REPLY else None
        content_purpose: str
        if metadata_reply is not None and metadata_reply.is_metadata_only:
            experience_signal = detect_product_experience_signal("")
            content_purpose = ContentPurpose.METADATA_REPLY
        else:
            experience_signal = detect_product_experience_signal(
                signal_text,
                parent_text=parent_signal_text,
                allow_context_inheritance=review.record_type == RecordType.REPLY and parent_allows_inheritance,
            )
            content_purpose = classify_content_purpose(
                signal_text,
                has_experience_signal=experience_signal.has_signal,
                promotional=promotional,
            )
        duplicate_of = self._find_duplicate(review, normalized_text)
        duplicate = duplicate_of is not None
        supported_record_type = review.record_type in {RecordType.THREAD, RecordType.REPLY}
        automatic_reason = _automatic_exclusion_reason(
            is_empty=is_empty,
            invalid_encoding=invalid_encoding,
            official=official,
            product_related=product_related,
            noise=noise,
            promotional=promotional,
            low_information=low_information,
            duplicate=duplicate,
            supported_record_type=supported_record_type,
            has_product_experience_signal=experience_signal.has_signal,
            content_purpose=content_purpose,
        )
        automatic_eligible = automatic_reason == ExclusionReason.NONE
        score = _quality_score(
            is_empty=is_empty,
            invalid_encoding=invalid_encoding,
            official=official,
            product_related=product_related,
            noise=noise,
            promotional=promotional,
            low_information=low_information,
            duplicate=duplicate,
            published_at=review.published_at,
            context_sufficient=context.has_parent_context,
            has_product_experience_signal=experience_signal.has_signal,
        )
        manual_override = bool(existing and existing.manual_override and existing.manual_eligible is not None)
        eligible = bool(existing.manual_eligible) if manual_override and existing is not None else automatic_eligible
        exclusion_reason = automatic_reason
        if manual_override:
            exclusion_reason = (
                ExclusionReason.NONE
                if eligible
                else (automatic_reason if automatic_reason != ExclusionReason.NONE else ExclusionReason.OTHER)
            )
        has_meaningful_text = not is_empty and not invalid_encoding and not noise
        flags = {
            "automatic_eligible": automatic_eligible,
            "automatic_exclusion_reason": automatic_reason,
            "context_sufficient": context.has_parent_context,
            "invalid_encoding": invalid_encoding,
            "manual_override_applied": manual_override,
            "published_at_present": review.published_at is not None,
            "has_product_experience_signal": experience_signal.has_signal,
            "context_required": experience_signal.context_required,
            "content_purpose": content_purpose,
            "candidate_aspects": list(experience_signal.candidate_aspects),
            "experience_signal_reasons": list(experience_signal.matched_terms),
            "candidate_metadata": metadata_reply.candidate_metadata if metadata_reply is not None else {},
            "platform_boilerplate_removed": list(cleaning_result.removed_lines),
        }
        self._remember(review, normalized_text)

        if not persist:
            return GovernanceDecision(
                review_id=review.id,
                record_type=review.record_type,
                content_preview=normalized_text[:100],
                eligible=eligible,
                exclusion_reason=exclusion_reason,
                quality_score=score,
                is_official=official,
                is_low_information=low_information,
                is_promotional=promotional,
                is_noise=noise,
                is_product_related=product_related,
                has_product_experience_signal=experience_signal.has_signal,
                context_required=experience_signal.context_required,
                content_purpose=content_purpose,
                candidate_aspects=experience_signal.candidate_aspects,
                is_duplicate=duplicate,
                is_empty=is_empty,
            )

        processed_at = timezone.now()
        quality_defaults: dict[str, Any] = {
            "normalized_text": normalized_text,
            "has_meaningful_text": has_meaningful_text,
            "is_product_related": product_related,
            "has_product_experience_signal": experience_signal.has_signal,
            "context_required": experience_signal.context_required,
            "content_purpose": content_purpose,
            "is_official_content": official,
            "is_low_information": low_information,
            "is_navigation_or_page_noise": noise,
            "is_promotional": promotional,
            "is_duplicate": duplicate,
            "duplicate_of": duplicate_of,
            "eligible_for_ai": eligible,
            "exclusion_reason": exclusion_reason,
            "quality_score": score,
            "flags_json": flags,
            "processor_version": GOVERNANCE_PROCESSOR_VERSION,
            "processed_at": processed_at,
        }
        with transaction.atomic():
            quality, _created = ReviewQuality.objects.update_or_create(review=review, defaults=quality_defaults)
            ReviewQualityRun.objects.update_or_create(
                review=review,
                processor_version=GOVERNANCE_PROCESSOR_VERSION,
                defaults={
                    "normalized_text": normalized_text,
                    "has_product_experience_signal": experience_signal.has_signal,
                    "context_required": experience_signal.context_required,
                    "content_purpose": content_purpose,
                    "eligible_for_ai": eligible,
                    "exclusion_reason": exclusion_reason,
                    "quality_score": score,
                    "flags_json": flags,
                    "processed_at": processed_at,
                },
            )
            AnalysisCorpusItem.objects.update_or_create(
                review=review,
                defaults={
                    "quality": quality,
                    "product_id": review.product_id,
                    "source_id": review.source_id,
                    "record_type": review.record_type,
                    "author_role": review.author_role,
                    "normalized_text": normalized_text,
                    "context_text": context.as_text(),
                    "eligible": eligible,
                    "exclusion_reason": exclusion_reason,
                    "quality_score": score,
                    "corpus_version": CORPUS_VERSION,
                },
            )
        return _decision_from_quality(quality, reused=False)


def _batch_result(decisions: list[GovernanceDecision]) -> GovernanceBatchResult:
    reasons = Counter(decision.exclusion_reason for decision in decisions if not decision.eligible)
    return GovernanceBatchResult(
        total=len(decisions),
        eligible=sum(decision.eligible for decision in decisions),
        excluded=sum(not decision.eligible for decision in decisions),
        official=sum(decision.is_official for decision in decisions),
        low_information=sum(decision.is_low_information for decision in decisions),
        promotional=sum(decision.is_promotional for decision in decisions),
        noise=sum(decision.is_noise for decision in decisions),
        product_not_matched=sum(not decision.is_product_related for decision in decisions),
        duplicate=sum(decision.is_duplicate for decision in decisions),
        empty=sum(decision.is_empty for decision in decisions),
        reused=sum(decision.reused for decision in decisions),
        exclusion_reasons=dict(sorted(reasons.items())),
        decisions=tuple(decisions),
    )


def process_reviews(
    queryset: QuerySet[ReviewRecord],
    *,
    batch_size: int = 100,
    persist: bool = True,
    reprocess: bool = False,
) -> GovernanceBatchResult:
    processor = GovernanceProcessor()
    decisions = [
        processor.process(review, persist=persist, force=reprocess)
        for review in queryset.select_related("source", "source_target", "product")
        .order_by("id")
        .iterator(chunk_size=batch_size)
    ]
    return _batch_result(decisions)


def apply_manual_override(review_id: int, *, eligible: bool, reason: str) -> GovernanceDecision:
    review = ReviewRecord.objects.select_related("source", "source_target", "product").get(pk=review_id)
    quality = ReviewQuality.objects.filter(review=review).first()
    if quality is None:
        GovernanceProcessor().process(review, persist=True, force=True)
        quality = ReviewQuality.objects.get(review=review)
    quality.manual_override = True
    quality.manual_eligible = eligible
    quality.manual_reason = reason.strip()
    quality.save(update_fields=("manual_override", "manual_eligible", "manual_reason", "updated_at"))
    return GovernanceProcessor().process(review, persist=True, force=True)


def clear_manual_override(review_id: int) -> GovernanceDecision:
    review = ReviewRecord.objects.select_related("source", "source_target", "product").get(pk=review_id)
    quality = ReviewQuality.objects.get(review=review)
    quality.manual_override = False
    quality.manual_eligible = None
    quality.manual_reason = ""
    quality.save(update_fields=("manual_override", "manual_eligible", "manual_reason", "updated_at"))
    return GovernanceProcessor().process(review, persist=True, force=True)
