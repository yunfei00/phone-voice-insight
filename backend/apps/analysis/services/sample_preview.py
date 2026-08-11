"""Build and render deterministic Phase 5 evaluation-sample previews without AI calls."""

# ruff: noqa: RUF001

from __future__ import annotations

from dataclasses import asdict, dataclass

from django.db.models import QuerySet

from apps.analysis.services.evaluation_samples import load_evaluation_sample
from apps.analysis.services.sampling import sample_coverage, select_corpus_items
from apps.reviews.models import AnalysisCorpusItem, RecordType
from apps.reviews.services.context_builder import find_parent_review


@dataclass(frozen=True)
class SamplePreviewItem:
    review_id: int
    record_type: str
    current_content: str
    necessary_context: str
    experience_signal_reason: str
    candidate_aspects: tuple[str, ...]
    content_purpose: str
    context_required: bool

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def select_phase5_poc_v2(queryset: QuerySet[AnalysisCorpusItem]) -> list[AnalysisCorpusItem]:
    candidates = queryset.filter(
        eligible=True,
        quality__eligible_for_ai=True,
        quality__has_product_experience_signal=True,
    )
    selected = select_corpus_items(candidates, limit=20, seed=20260808)
    coverage = sample_coverage(selected)
    if len(selected) != 20:
        raise ValueError("PHASE5_POC_V2_REQUIRES_TWENTY_ITEMS")
    if coverage["thread"] < 5 or coverage["reply"] < 10:
        raise ValueError("PHASE5_POC_V2_RECORD_TYPE_COVERAGE_FAILED")
    if coverage["context_dependent_candidates"] < 3:
        raise ValueError("PHASE5_POC_V2_CONTEXT_COVERAGE_FAILED")
    if coverage["multi_aspect_candidates"] < 2:
        raise ValueError("PHASE5_POC_V2_MULTI_ASPECT_COVERAGE_FAILED")
    return selected


def _necessary_context(item: AnalysisCorpusItem) -> str:
    if item.record_type == RecordType.THREAD or not item.quality.context_required:
        return "N/A"
    parent = find_parent_review(item.review)
    if parent is None:
        return "N/A"
    sections = []
    if parent.title:
        sections.append(f"父帖标题：{parent.title}")
    if parent.content:
        sections.append(f"父帖正文：{parent.content}")
    return "\n".join(sections) or "N/A"


def preview_item(item: AnalysisCorpusItem) -> SamplePreviewItem:
    flags = item.quality.flags_json
    reasons = flags.get("experience_signal_reasons", [])
    aspects = flags.get("candidate_aspects", [])
    safe_reasons = tuple(value for value in reasons if isinstance(value, str)) if isinstance(reasons, list) else ()
    safe_aspects = tuple(value for value in aspects if isinstance(value, str)) if isinstance(aspects, list) else ()
    reason = "；".join(safe_reasons) or "确定性体验信号规则命中"
    return SamplePreviewItem(
        review_id=item.review_id,
        record_type=item.record_type,
        current_content=item.review.content,
        necessary_context=_necessary_context(item),
        experience_signal_reason=reason,
        candidate_aspects=safe_aspects,
        content_purpose=item.quality.content_purpose,
        context_required=item.quality.context_required,
    )


def load_sample_preview(sample_version: str) -> list[SamplePreviewItem]:
    sample = load_evaluation_sample(sample_version)
    queryset = AnalysisCorpusItem.objects.filter(review_id__in=sample.review_ids).select_related(
        "review", "quality", "product", "source"
    )
    item_by_review_id = {item.review_id: item for item in queryset}
    if set(item_by_review_id) != set(sample.review_ids):
        raise ValueError("EVALUATION_SAMPLE_RECORD_MISSING")
    return [preview_item(item_by_review_id[review_id]) for review_id in sample.review_ids]


def _quote(value: str) -> str:
    return "\n".join(f"> {line}" if line else ">" for line in value.splitlines()) or "> N/A"


def render_sample_preview_markdown(items: list[AnalysisCorpusItem]) -> str:
    lines = [
        "# Phase 5 PoC v2 样本预览",
        "",
        "- Sample version: `phase5-poc-v2`",
        "- Seed: `20260808`",
        f"- Count: `{len(items)}`",
        "- AI status: `NOT_RUN`",
        "",
    ]
    for index, item in enumerate(items, start=1):
        preview = preview_item(item)
        lines.extend(
            (
                f"## Sample {index:02d}",
                "",
                f"- Review ID: `{preview.review_id}`",
                f"- Record Type: `{preview.record_type}`",
                f"- Content Purpose: `{preview.content_purpose}`",
                "",
                "### 当前正文",
                "",
                _quote(preview.current_content),
                "",
                "### 必要上下文",
                "",
                _quote(preview.necessary_context),
                "",
                "### 产品体验 Signal",
                "",
                f"- 判定依据：{preview.experience_signal_reason}",
                f"- 候选 Aspect：{', '.join(preview.candidate_aspects)}",
                f"- Context Required：{'YES' if preview.context_required else 'NO'}",
                "",
                "---",
                "",
            )
        )
    return "\n".join(lines).rstrip() + "\n"
