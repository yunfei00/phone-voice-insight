"""High-confidence navigation and page-residue detection."""

# ruff: noqa: RUF001

from __future__ import annotations

import re

from apps.reviews.services.text_normalizer import normalize_text

_EXACT_UI_TEXT = frozenset(
    {
        "举报",
        "回复",
        "点赞",
        "分享",
        "收藏",
        "加载更多",
        "查看更多",
        "复制链接",
    }
)
_UI_WITH_COUNT = re.compile(r"^(?:举报|回复|点赞|分享|收藏)\s*\d{0,6}$")
_REPEATED_UI = re.compile(r"^(?:点赞|收藏|分享){2,4}$")
_METADATA_ONLY = re.compile(r"^(?:发表于\s*\S{1,24}|来自[:：]\s*\S{1,30})$")
_SEPARATOR = re.compile(r"[|｜·•\s]+")
_EDGE_PUNCTUATION = re.compile(r"^[\W_]+|[\W_]+$", re.UNICODE)


def is_navigation_or_page_noise(value: str | None) -> bool:
    text = normalize_text(value)
    if not text:
        return False
    canonical = _EDGE_PUNCTUATION.sub("", text)
    if (
        canonical in _EXACT_UI_TEXT
        or _UI_WITH_COUNT.fullmatch(canonical)
        or _REPEATED_UI.fullmatch(canonical)
        or _METADATA_ONLY.fullmatch(text)
    ):
        return True
    if len(text) <= 32:
        parts = tuple(part for part in _SEPARATOR.split(text) if part)
        if len(parts) >= 2 and all(part in _EXACT_UI_TEXT or _UI_WITH_COUNT.fullmatch(part) for part in parts):
            return True
    return False
