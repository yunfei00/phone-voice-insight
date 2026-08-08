"""Conservative text normalization that never changes the source record."""

from __future__ import annotations

import html
import re
import unicodedata

_ZERO_WIDTH = re.compile(r"[\u200b-\u200d\u2060\ufeff]")
_HORIZONTAL_WHITESPACE = re.compile(r"[^\S\r\n]+")
_EXCESS_BLANK_LINES = re.compile(r"\n{3,}")


def normalize_text(value: str | None) -> str:
    """Normalize encoding and whitespace without rewriting meaning."""

    if not value:
        return ""
    normalized = html.unescape(value)
    normalized = unicodedata.normalize("NFC", normalized)
    normalized = _ZERO_WIDTH.sub("", normalized)
    normalized = normalized.replace("\r\n", "\n").replace("\r", "\n")
    lines = [_HORIZONTAL_WHITESPACE.sub(" ", line).strip() for line in normalized.split("\n")]
    normalized = "\n".join(lines).strip()
    return _EXCESS_BLANK_LINES.sub("\n\n", normalized)
