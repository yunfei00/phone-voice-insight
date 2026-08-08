"""Validate that every evidence span is verbatim and traceable."""

from __future__ import annotations

from dataclasses import dataclass

from ai.schemas.review_analysis import ReviewAnalysisInput, ReviewAnalysisOutput


@dataclass(frozen=True)
class EvidenceValidationError:
    aspect: str
    field: str
    message: str


def validate_evidence(
    request: ReviewAnalysisInput,
    output: ReviewAnalysisOutput,
) -> tuple[EvidenceValidationError, ...]:
    context_sources = {
        request.thread_review_id: request.thread_content,
        request.parent_review_id: request.parent_content,
    }
    errors: list[EvidenceValidationError] = []
    for item in output.aspects:
        aspect = item.aspect.value
        if item.evidence_text not in request.content:
            errors.append(EvidenceValidationError(aspect, "evidence_text", "evidence is not verbatim current content"))
        if item.context_dependent:
            if not item.context_evidence_review_id or not item.context_evidence_text:
                errors.append(EvidenceValidationError(aspect, "context_evidence", "context evidence is required"))
                continue
            referenced = context_sources.get(item.context_evidence_review_id, "")
            if not referenced or item.context_evidence_text not in referenced:
                errors.append(
                    EvidenceValidationError(
                        aspect, "context_evidence_text", "context evidence is not verbatim referenced content"
                    )
                )
        elif item.context_evidence_review_id or item.context_evidence_text:
            errors.append(
                EvidenceValidationError(aspect, "context_dependent", "context evidence requires context_dependent")
            )
    return tuple(errors)
