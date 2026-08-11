"""Render privacy-minimized Markdown for human Phase 5 review."""

# ruff: noqa: RUF001

from __future__ import annotations

from apps.analysis.models import AnalysisBatch, AnalysisResult
from apps.analysis.services.input_builder import build_review_analysis_input
from apps.reviews.models import RecordType


def _quote(value: str) -> str:
    safe = value.replace("<", "&lt;").replace(">", "&gt;")
    return "\n".join(f"> {line}" if line else ">" for line in safe.splitlines()) or "> （空）"


def _necessary_context(result: AnalysisResult) -> str:
    if result.corpus_item is None or result.review.record_type == RecordType.THREAD:
        return "> N/A"
    request = build_review_analysis_input(result.corpus_item)
    sections: list[str] = []
    if request.thread_title:
        sections.extend(("父帖标题：", "", _quote(request.thread_title)))
    if request.thread_content:
        sections.extend(("主题正文：", "", _quote(request.thread_content)))
    if request.parent_content and request.parent_content != request.thread_content:
        sections.extend(("父级回复正文：", "", _quote(request.parent_content)))
    return "\n\n".join(sections) if sections else "> N/A"


def _aspect_markdown(result: AnalysisResult) -> list[str]:
    lines: list[str] = []
    aspects = list(result.aspects.all())
    if not aspects:
        return ["AI Result: 无结构化维度", "", f"Status: {result.status}", f"Error: {result.error_code or '—'}"]
    for index, aspect in enumerate(aspects, start=1):
        if len(aspects) > 1:
            lines.extend((f"#### Aspect Result {index}", ""))
        lines.extend(
            (
                f"Aspect: {aspect.aspect}",
                "",
                f"Sentiment: {aspect.sentiment}",
                "",
                f"Issue Category: {aspect.issue_category or '—'}",
                "",
                f"Issue Summary: {aspect.issue_summary or '—'}",
                "",
                f"Usage Scenario: {aspect.usage_scenario or '—'}",
                "",
                "Evidence:",
                "",
                _quote(aspect.evidence_text),
                "",
                f"Context Dependent: {str(aspect.context_dependent).lower()}",
                "",
                "Context Evidence:",
                "",
                _quote(aspect.context_evidence_text) if aspect.context_evidence_text else "> —",
                "",
                f"Context Evidence Review ID: {aspect.context_evidence_review_id or '—'}",
                "",
                f"Confidence: {aspect.confidence}",
                "",
            )
        )
    return lines


def render_batch_review_markdown(batch: AnalysisBatch) -> str:
    results = list(
        batch.results.select_related("review", "corpus_item").prefetch_related("aspects").order_by("created_at", "id")
    )
    lines = [
        "# Phase 5 PoC v3 真实 AI 结果人工审核",
        "",
        f"Batch ID: {batch.id}",
        f"Provider: {batch.provider}",
        f"Model: {batch.model_name}",
        f"Prompt: {batch.prompt_version}",
        f"Samples: {len(results)}",
        "Human evaluation status: NOT_EVALUATED",
        "",
        "本文件仅包含评论正文、必要上下文和结构化分析结果。",
        "",
    ]
    for index, result in enumerate(results, start=1):
        lines.extend(
            (
                f"## Sample {index:02d}",
                "",
                "### 基本信息",
                "",
                f"Review ID: {result.review_id}",
                "",
                f"Record Type: {result.review.record_type}",
                "",
                f"Content Purpose: {result.content_purpose}",
                "",
                "### 当前用户原文",
                "",
                _quote(result.review.content),
                "",
                "### 治理后的 normalized_text",
                "",
                _quote(result.corpus_item.normalized_text if result.corpus_item else ""),
                "",
                "### 必要上下文",
                "",
                _necessary_context(result),
                "",
                "### AI结果",
                "",
            )
        )
        lines.extend(_aspect_markdown(result))
        lines.extend(
            (
                "",
                "### 人工审核",
                "",
                "- [ ] Aspect 正确  - [ ] Aspect 错误",
                "- [ ] Sentiment 正确  - [ ] Sentiment 错误",
                "- [ ] Issue 正确  - [ ] Issue 错误",
                "- [ ] Scenario 正确  - [ ] Scenario 错误",
                "- [ ] Evidence 正确  - [ ] Evidence 错误",
                "- [ ] Context 正确  - [ ] Context 错误",
                "- [ ] Hallucination 有  - [ ] Hallucination 无",
                "",
                "备注：",
                "",
                "---",
                "",
            )
        )
    return "\n".join(lines).rstrip() + "\n"
