"""Business-level validation beyond Pydantic field constraints."""

from __future__ import annotations

from dataclasses import dataclass

from ai.schemas.review_analysis import ReviewAnalysisInput, ReviewAnalysisOutput


@dataclass(frozen=True)
class AnalysisValidationError:
    field: str
    message: str


def validate_analysis(
    request: ReviewAnalysisInput,
    output: ReviewAnalysisOutput,
) -> tuple[AnalysisValidationError, ...]:
    errors: list[AnalysisValidationError] = []
    if request.is_official or request.author_role == "OFFICIAL" or request.record_type == "OFFICIAL_REPLY":
        errors.append(AnalysisValidationError("is_official", "official content cannot enter user analysis"))
    if output.product_model != request.product_model:
        errors.append(AnalysisValidationError("product_model", "output product does not match input"))
    if output.is_valid_content != bool(output.aspects):
        errors.append(AnalysisValidationError("is_valid_content", "validity must agree with aspects"))
    seen: set[str] = set()
    for item in output.aspects:
        key = item.aspect.value
        if key in seen:
            errors.append(AnalysisValidationError("aspects", "each aspect must appear at most once"))
        seen.add(key)
        if not item.evidence_text:
            errors.append(AnalysisValidationError("evidence_text", "evidence cannot be empty"))
        if item.context_dependent != bool(item.context_evidence_text and item.context_evidence_review_id):
            errors.append(AnalysisValidationError("context_dependent", "context fields are inconsistent"))
    return tuple(errors)
