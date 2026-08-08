"""Load immutable, versioned review-analysis prompts."""

from __future__ import annotations

import re
from pathlib import Path

import ai

_PROMPT_VERSION = re.compile(r"^review_analysis_v\d+$")
_PROMPT_ROOT = Path(ai.__file__).resolve().parent / "prompts"


def load_review_prompt(prompt_version: str) -> str:
    if not _PROMPT_VERSION.fullmatch(prompt_version):
        raise ValueError("INVALID_PROMPT_VERSION")
    path = _PROMPT_ROOT / f"{prompt_version}.md"
    if not path.is_file():
        raise ValueError("PROMPT_NOT_FOUND")
    return path.read_text(encoding="utf-8")
