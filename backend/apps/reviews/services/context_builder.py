"""Build structured, non-AI context for a review record."""

from __future__ import annotations

from dataclasses import dataclass

from apps.reviews.models import RecordType, ReviewRecord
from apps.reviews.services.platform_boilerplate_cleaner import clean_platform_boilerplate
from apps.reviews.services.text_normalizer import normalize_text

_CONTEXT_LIMIT = 600


@dataclass(frozen=True)
class AnalysisContext:
    thread_title: str
    thread_content: str
    parent_content: str
    current_content: str
    record_type: str
    author_role: str
    published_at: str
    device_source: str
    has_parent_context: bool

    def as_text(self) -> str:
        fields = (
            ("帖子标题", self.thread_title),
            ("帖子正文", self.thread_content),
            ("父级内容", self.parent_content),
            ("当前内容", self.current_content),
            ("记录类型", self.record_type),
            ("作者角色", self.author_role),
            ("发布时间", self.published_at),
            ("设备来源", self.device_source),
        )
        return "\n".join(f"{label}: {value}" for label, value in fields if value)


def find_parent_review(review: ReviewRecord) -> ReviewRecord | None:
    if not review.parent_external_id:
        return None
    return (
        ReviewRecord.objects.filter(
            source_id=review.source_id,
            external_id=review.parent_external_id,
        )
        .order_by("id")
        .first()
    )


def _raw_text(review: ReviewRecord, key: str) -> str:
    value = review.raw_data.get(key) if isinstance(review.raw_data, dict) else None
    return normalize_text(value if isinstance(value, str) else "")[:_CONTEXT_LIMIT]


def _content(value: str | None) -> str:
    return clean_platform_boilerplate(value).text[:_CONTEXT_LIMIT]


def build_analysis_context(review: ReviewRecord, *, parent: ReviewRecord | None = None) -> AnalysisContext:
    parent = parent or find_parent_review(review)
    is_thread = review.record_type == RecordType.THREAD
    thread_title = normalize_text(review.title if is_thread else (parent.title if parent else ""))[:_CONTEXT_LIMIT]
    thread_content = _content(review.content if is_thread else (parent.content if parent else ""))
    parent_content = _content(parent.content if parent and not is_thread else "")
    device_source = _raw_text(review, "device_source") or (_raw_text(parent, "device_source") if parent else "")
    return AnalysisContext(
        thread_title=thread_title,
        thread_content=thread_content,
        parent_content=parent_content,
        current_content=_content(review.content),
        record_type=review.record_type,
        author_role=review.author_role,
        published_at=review.published_at.isoformat() if review.published_at else "",
        device_source=device_source,
        has_parent_context=is_thread or parent is not None,
    )
