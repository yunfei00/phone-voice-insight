"""Render privacy-minimized Markdown for human Phase 5 review."""

# ruff: noqa: RUF001

from __future__ import annotations

from apps.analysis.models import AnalysisBatch, AnalysisResult


def _quote(value: str) -> str:
    safe = value.replace("<", "&lt;").replace(">", "&gt;")
    return "\n".join(f"> {line}" if line else ">" for line in safe.splitlines()) or "> （空）"


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
        "# Phase 5 PoC 人工审核 v1",
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
                "### 当前用户原文",
                "",
                _quote(result.review.content),
                "",
                "### 上下文",
                "",
                _quote(result.corpus_item.context_text if result.corpus_item else ""),
                "",
                "### AI 分析",
                "",
            )
        )
        lines.extend(_aspect_markdown(result))
        lines.extend(
            (
                "",
                "### 人工审核",
                "",
                "- [ ] Aspect 正确",
                "- [ ] Sentiment 正确",
                "- [ ] Issue 正确",
                "- [ ] Scenario 正确",
                "- [ ] Evidence 正确",
                "- [ ] Context 使用正确",
                "- [ ] 无幻觉",
                "",
                "人工备注：",
                "",
                "---",
                "",
            )
        )
    return "\n".join(lines).rstrip() + "\n"
