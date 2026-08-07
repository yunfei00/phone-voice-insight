"""荣耀俱乐部原始记录标准化。"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime
from typing import Any

from collectors.base import NormalizedReview, RawRecord
from collectors.honor_club.role_mapper import is_official_role, map_author_role

_WHITESPACE_PATTERN = re.compile(r"\s+")


def normalize_match_text(value: str) -> str:
    return _WHITESPACE_PATTERN.sub("", value).casefold()


def is_power2_related(*, title: str, content: str, topic_tags: list[str], aliases: list[str]) -> bool:
    if any("荣耀power2" in normalize_match_text(tag) for tag in topic_tags):
        return True
    haystack = normalize_match_text(f"{title}\n{content}")
    return any(normalize_match_text(alias) in haystack for alias in aliases if alias.strip())


def build_fallback_external_id(
    *,
    thread_id: str,
    floor: str,
    published_at_raw: str,
    content: str,
) -> str:
    material = "\x1f".join((thread_id, floor, published_at_raw, _WHITESPACE_PATTERN.sub(" ", content).strip()))
    return f"honor_fallback:{hashlib.sha256(material.encode('utf-8')).hexdigest()[:32]}"


def normalize_honor_record(raw_record: RawRecord) -> NormalizedReview:
    payload = raw_record.payload
    role_text = str(payload.get("author_role_text", ""))
    author_role = map_author_role(role_text)
    is_official = is_official_role(author_role)
    record_type = raw_record.record_type
    if record_type == "REPLY" and is_official:
        record_type = "OFFICIAL_REPLY"

    published_at = payload.get("published_at")
    if published_at is not None and not isinstance(published_at, datetime):
        published_at = None

    raw_data = dict(payload.get("raw_data", {}))
    raw_data["author_role_text"] = role_text
    return NormalizedReview(
        external_id=raw_record.external_id,
        parent_external_id=payload.get("parent_external_id"),
        record_type=record_type,
        title=str(payload.get("title", "")),
        content=str(payload.get("content", "")),
        published_at=published_at,
        author_role=author_role,
        is_official=is_official,
        software_version=str(payload.get("software_version", "")),
        source_url=str(payload.get("source_url", "")),
        raw_data=raw_data,
    )


def safe_raw_data(**values: Any) -> dict[str, Any]:
    """删除空值并确保采集器不会持久化用户昵称或位置。"""

    blocked_keys = {"author_name", "author_nickname", "nickname", "location", "ip", "avatar"}
    return {key: value for key, value in values.items() if key not in blocked_keys and value not in (None, "", [], {})}
