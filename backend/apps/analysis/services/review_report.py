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
            lines.extend((f"### Aspect Result {index}", ""))
        lines.extend(
            (
                f"Aspect: {aspect.aspect}",
                "",
                f"Sentiment: {aspect.sentiment}",
                "",
                f"Issue category: {aspect.issue_category or '—'}",
                "",
                f"Issue summary: {aspect.issue_summary or '—'}",
                "",
                f"Usage scenario: {aspect.usage_scenario or '—'}",
                "",
                "Evidence:",
                "",
                _quote(aspect.evidence_text),
                "",
                f"Context dependent: {str(aspect.context_dependent).lower()}",
                "",
                "Context evidence:",
                "",
                _quote(aspect.context_evidence_text) if aspect.context_evidence_text else "> —",
                "",
                f"Context evidence Review ID: {aspect.context_evidence_review_id or '—'}",
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
        "本文件仅包含反馈正文、必要上下文和结构化结果；不包含昵称、用户 ID、头像、Cookie、IP 或 Token。",
        "",
    ]
    for index, result in enumerate(results, start=1):
        lines.extend(
            (
                f"## Sample {index:02d}",
                "",
                f"Review ID: {result.review_id}",
                "",
                f"Record Type: {result.review.record_type}",
                "",
                "Current content:",
                "",
                _quote(result.review.content),
                "",
                "Context:",
                "",
                _quote(result.corpus_item.context_text if result.corpus_item else ""),
                "",
                "AI Result:",
                "",
            )
        )
        lines.extend(_aspect_markdown(result))
        lines.extend(
            (
                "",
                "人工审核：",
                "",
                "- [ ] Aspect 正确",
                "- [ ] Sentiment 正确",
                "- [ ] Issue 正确",
                "- [ ] Scenario 正确",
                "- [ ] Evidence 正确",
                "- [ ] 无幻觉",
                "",
                "人工备注：",
                "",
                "---",
                "",
            )
        )
    return "\n".join(lines).rstrip() + "\n"
