"""Load fixed evaluation sample manifests without embedding review content in code."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from django.conf import settings


@dataclass(frozen=True)
class EvaluationSample:
    sample_version: str
    seed: int
    review_ids: tuple[int, ...]


_SAMPLE_FILES = {"phase5-poc-v1": "phase5-poc-sample-v1.json"}


def load_evaluation_sample(sample_version: str) -> EvaluationSample:
    file_name = _SAMPLE_FILES.get(sample_version)
    if file_name is None:
        raise ValueError("UNKNOWN_EVALUATION_SAMPLE")
    candidates = (
        Path(settings.BASE_DIR) / "docs" / "evaluation" / file_name,
        Path(settings.BASE_DIR).parent / "docs" / "evaluation" / file_name,
    )
    manifest_path = next((path for path in candidates if path.is_file()), None)
    if manifest_path is None:
        raise ValueError("EVALUATION_SAMPLE_NOT_INSTALLED")
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("EVALUATION_SAMPLE_INVALID") from exc
    if not isinstance(payload, dict):
        raise ValueError("EVALUATION_SAMPLE_INVALID")
    seed = payload.get("seed")
    review_ids = payload.get("review_ids")
    if (
        payload.get("sample_version") != sample_version
        or not isinstance(seed, int)
        or not isinstance(review_ids, list)
        or len(review_ids) != 20
        or any(not isinstance(review_id, int) or review_id <= 0 for review_id in review_ids)
        or len(set(review_ids)) != len(review_ids)
    ):
        raise ValueError("EVALUATION_SAMPLE_INVALID")
    return EvaluationSample(sample_version=sample_version, seed=seed, review_ids=tuple(review_ids))
