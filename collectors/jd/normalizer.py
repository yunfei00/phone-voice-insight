"""将已映射的京东评论字段转换为通用评论契约。"""

from __future__ import annotations

import re
from datetime import datetime
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup

from collectors.base import NormalizedReview, RawRecord
from collectors.jd.variant_mapper import extract_variant_attributes

_CONTROL_PATTERN = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_MULTI_SPACE_PATTERN = re.compile(r"[^\S\n]+")
_TIME_FORMATS = ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M")


def clean_review_content(value: str) -> str:
    text = BeautifulSoup(value, "html.parser").get_text("\n")
    text = _CONTROL_PATTERN.sub("", text).replace("\r\n", "\n").replace("\r", "\n")
    lines = [_MULTI_SPACE_PATTERN.sub(" ", line).strip() for line in text.split("\n")]
    return "\n".join(line for line in lines if line).strip()


def parse_jd_datetime(value: str) -> datetime | None:
    if not value:
        return None
    candidate = value.strip()
    try:
        parsed = datetime.fromisoformat(candidate.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=ZoneInfo("Asia/Shanghai"))
    except ValueError:
        pass
    for pattern in _TIME_FORMATS:
        try:
            return datetime.strptime(candidate, pattern).replace(tzinfo=ZoneInfo("Asia/Shanghai"))
        except ValueError:
            continue
    return None


def _media_count(value: object) -> int:
    return len(value) if isinstance(value, list) else 0


def normalize_jd_record(raw_record: RawRecord) -> NormalizedReview:
    payload = raw_record.payload
    content = clean_review_content(str(payload.get("content", "")))
    rating: float | None = None
    warnings: list[str] = []
    if raw_record.record_type == "REVIEW" and payload.get("rating") not in (None, ""):
        try:
            candidate = float(payload["rating"])
            if 0 <= candidate <= 5:
                rating = candidate
            else:
                warnings.append("rating_out_of_range")
        except (TypeError, ValueError):
            warnings.append("rating_invalid")

    is_append = raw_record.record_type == "APPEND_REVIEW"
    time_key = "append_time_raw" if is_append else "creation_time_raw"
    time_raw = str(payload.get(time_key, ""))
    published_at = parse_jd_datetime(time_raw)
    if time_raw and published_at is None:
        warnings.append("timestamp_unparsed")

    images = payload.get("images", [])
    videos = payload.get("videos", [])
    product_color = str(payload.get("product_color", ""))
    product_size = str(payload.get("product_size", ""))
    raw_data = {
        "jd_comment_id": str(payload.get("comment_id", "")),
        "jd_sku_id": str(payload.get("variant_external_id", "")),
        "product_color": product_color,
        "product_size": product_size,
        "reference_name": str(payload.get("reference_name", "")),
        "useful_vote_count": payload.get("useful_vote_count", 0),
        "reply_count": payload.get("reply_count", 0),
        "has_image": bool(images),
        "image_count": _media_count(images),
        "has_video": bool(videos),
        "video_count": _media_count(videos),
        "has_analyzable_text": bool(content),
        time_key: time_raw,
    }
    if warnings:
        raw_data["parse_warnings"] = warnings
    return NormalizedReview(
        external_id=raw_record.external_id,
        parent_external_id=f"jd_review:{payload['comment_id']}" if is_append else None,
        record_type=raw_record.record_type,
        content=content,
        rating=rating,
        published_at=published_at,
        author_role="USER",
        is_append_review=is_append,
        variant_external_id=str(payload.get("variant_external_id", "")),
        variant_attributes=extract_variant_attributes(product_size=product_size, product_color=product_color),
        raw_data={key: value for key, value in raw_data.items() if value not in (None, "", [], {})},
    )
