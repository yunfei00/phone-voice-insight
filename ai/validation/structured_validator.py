"""跨字段业务校验：证据、型号归属和隐私摘要。"""

import re
from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError

from ai.schemas.structured_analysis import StructuredAnalysisPayload

_PII_PATTERNS = (
    re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)"),
    re.compile(r"\b\d{17}[0-9Xx]\b"),
    re.compile(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}"),
)


@dataclass(frozen=True)
class StructuredValidationResult:
    valid: bool
    payload: StructuredAnalysisPayload | None
    errors: tuple[str, ...]
    review_required: bool


def validate_structured_payload(raw: Any, source_text: str) -> StructuredValidationResult:
    try:
        payload = StructuredAnalysisPayload.model_validate(raw)
    except ValidationError as exc:
        return StructuredValidationResult(False, None, tuple(error["msg"] for error in exc.errors()), True)

    errors: list[str] = []
    review_required = any(aspect.review_required for aspect in payload.aspects)
    for index, aspect in enumerate(payload.aspects):
        if source_text[aspect.evidence_start : aspect.evidence_end] != aspect.evidence_text:
            errors.append(f"aspects[{index}].evidence offset mismatch")
        if aspect.target_product and aspect.target_product not in payload.model_mentions:
            errors.append(f"aspects[{index}].target_product is not declared in model_mentions")
    if any(pattern.search(payload.summary) for pattern in _PII_PATTERNS):
        errors.append("summary contains personal information")
    return StructuredValidationResult(not errors, payload if not errors else None, tuple(errors), review_required or bool(errors))

