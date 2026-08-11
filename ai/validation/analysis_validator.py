"""Business-level validation beyond Pydantic field constraints."""

from __future__ import annotations

import re
from dataclasses import dataclass

from ai.schemas.review_analysis import ReviewAnalysisInput, ReviewAnalysisOutput

_EXPLICIT_NEGATIVE_MARKERS = re.compile(
    r"太差|很差|真差|不好|不行了|有问题|故障|慢|模糊|转圈|衰减|不匹配|没能解决|"
    r"电量.{0,8}(?:掉|下降)|掉电(?:太)?快|耗电(?:太)?快|发热|烫|卡顿|断流|没信号|无信号"
)


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
        if (
            request.content_purpose == "QUESTION"
            and item.sentiment.value == "NEGATIVE"
            and not _EXPLICIT_NEGATIVE_MARKERS.search(request.content)
        ):
            errors.append(
                AnalysisValidationError(
                    "sentiment",
                    "a pure question cannot be negative without an explicit negative statement",
                )
            )
    return tuple(errors)
