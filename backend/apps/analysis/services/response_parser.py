"""Safely parse and validate provider JSON output."""

from __future__ import annotations

import json
import re

from ai.schemas.review_analysis import ReviewAnalysisOutput

_FENCE = re.compile(r"^\s*```(?:json)?\s*(.*?)\s*```\s*$", re.DOTALL | re.IGNORECASE)


def parse_review_analysis_output(content: str) -> tuple[ReviewAnalysisOutput, dict[str, object]]:
    match = _FENCE.fullmatch(content)
    raw_json = match.group(1) if match else content.strip()
    payload = json.loads(raw_json)
    if not isinstance(payload, dict):
        raise ValueError("AI response must be a JSON object")
    output = ReviewAnalysisOutput.model_validate(payload)
    return output, payload
