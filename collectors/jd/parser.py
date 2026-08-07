"""京东商品页与评论响应的失败关闭解析器。"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from collectors.base import CollectorError, RawRecord
from collectors.jd.constants import (
    EXPECTED_BRAND_MARKERS,
    EXPECTED_PRODUCT_MARKERS,
    EXPECTED_SHOP_NAME,
    PRODUCT_HOST,
)


def _clean_text(value: Any) -> str:
    return " ".join(str(value or "").split())


def _path_value(value: Any, path: str, default: Any = None) -> Any:
    current = value
    for part in path.split("."):
        if not isinstance(current, Mapping) or part not in current:
            return default
        current = current[part]
    return current


def parse_product_page(html: str, *, product_id: str) -> RawRecord:
    soup = BeautifulSoup(html, "html.parser")
    title_node = soup.select_one('[itemprop="name"]') or soup.select_one("h1") or soup.select_one("title")
    title = _clean_text(title_node.get_text(" ") if title_node else "")
    brand_node = soup.select_one('[itemprop="brand"], [data-brand]')
    shop_node = soup.select_one('[data-shop-name], .shop-name, [class*="shopName"]')
    brand = _clean_text(brand_node.get("content") or brand_node.get_text(" ") if brand_node else "")
    shop = _clean_text(shop_node.get("data-shop-name") or shop_node.get_text(" ") if shop_node else "")
    canonical = soup.select_one('link[rel="canonical"]')
    canonical_url = str(canonical.get("href", "")) if canonical else ""
    if canonical_url.startswith("//"):
        canonical_url = f"https:{canonical_url}"
    canonical_product_id = urlparse(canonical_url).path.removeprefix("/").removesuffix(".html")
    return RawRecord(
        external_id=f"jd_product:{product_id}",
        record_type="PRODUCT_METADATA",
        payload={
            "product_id": canonical_product_id or product_id,
            "title": title,
            "brand": brand,
            "shop_name": shop,
            "canonical_url": canonical_url,
        },
    )


def validate_product_identity(record: RawRecord, *, product_id: str) -> None:
    payload = record.payload
    canonical_url = str(payload.get("canonical_url", ""))
    parsed = urlparse(canonical_url)
    checks = (
        payload.get("product_id") == product_id,
        parsed.scheme == "https" and parsed.hostname == PRODUCT_HOST,
        any(marker.casefold() in str(payload.get("title", "")).casefold() for marker in EXPECTED_PRODUCT_MARKERS),
        any(marker.casefold() in str(payload.get("brand", "")).casefold() for marker in EXPECTED_BRAND_MARKERS),
        payload.get("shop_name") == EXPECTED_SHOP_NAME,
    )
    if not all(checks):
        raise CollectorError("无法确认目标仍为荣耀 Power2 京东自营商品", code="PRODUCT_IDENTITY_NOT_VERIFIED")


def _required_path(field_map: Mapping[str, str], name: str) -> str:
    path = field_map.get(name, "")
    if not path:
        raise CollectorError(f"评论字段 {name} 尚未现场验证", code="RESPONSE_SCHEMA_NOT_VERIFIED")
    return path


def parse_comments_payload(payload: Any, *, field_map: Mapping[str, str]) -> list[RawRecord]:
    if not isinstance(payload, Mapping):
        raise CollectorError("评论响应顶层不是对象", code="RESPONSE_FORMAT_CHANGED")
    comments = _path_value(payload, _required_path(field_map, "comments"))
    if not isinstance(comments, list):
        raise CollectorError("评论列表字段不存在或类型变化", code="RESPONSE_FORMAT_CHANGED")

    records: list[RawRecord] = []
    for comment in comments:
        if not isinstance(comment, Mapping):
            raise CollectorError("评论记录不是对象", code="RESPONSE_FORMAT_CHANGED")
        comment_id = _clean_text(_path_value(comment, _required_path(field_map, "comment_id")))
        if not comment_id:
            raise CollectorError("评论缺少稳定 ID", code="RESPONSE_FORMAT_CHANGED")
        internal = {
            "comment_id": comment_id,
            "content": _clean_text(_path_value(comment, field_map.get("content", ""), "")),
            "rating": _path_value(comment, field_map.get("rating", "")),
            "creation_time_raw": _clean_text(_path_value(comment, field_map.get("creation_time", ""), "")),
            "variant_external_id": _clean_text(_path_value(comment, field_map.get("sku_id", ""), "")),
            "product_color": _clean_text(_path_value(comment, field_map.get("product_color", ""), "")),
            "product_size": _clean_text(_path_value(comment, field_map.get("product_size", ""), "")),
            "reference_name": _clean_text(_path_value(comment, field_map.get("reference_name", ""), "")),
            "useful_vote_count": _path_value(comment, field_map.get("useful_vote_count", ""), 0),
            "reply_count": _path_value(comment, field_map.get("reply_count", ""), 0),
            "images": _path_value(comment, field_map.get("images", ""), []),
            "videos": _path_value(comment, field_map.get("videos", ""), []),
        }
        records.append(RawRecord(external_id=f"jd_review:{comment_id}", record_type="REVIEW", payload=internal))

        append_value = _path_value(comment, field_map.get("append", ""))
        if append_value in (None, {}, []):
            continue
        append_items = append_value if isinstance(append_value, list) else [append_value]
        if not all(isinstance(item, Mapping) for item in append_items):
            raise CollectorError("追评字段结构变化", code="RESPONSE_FORMAT_CHANGED")
        for index, append in enumerate(append_items):
            append_id = _clean_text(_path_value(append, field_map.get("append_id", ""), ""))
            if not append_id:
                if len(append_items) > 1:
                    raise CollectorError("多个追评缺少稳定 ID", code="RESPONSE_FORMAT_CHANGED")
                external_id = f"jd_append:{comment_id}"
            else:
                external_id = f"jd_append:{append_id}"
            records.append(
                RawRecord(
                    external_id=external_id,
                    record_type="APPEND_REVIEW",
                    payload={
                        "comment_id": comment_id,
                        "append_index": index,
                        "content": _clean_text(_path_value(append, field_map.get("append_content", ""), "")),
                        "append_time_raw": _clean_text(_path_value(append, field_map.get("append_time", ""), "")),
                        "variant_external_id": internal["variant_external_id"],
                        "product_color": internal["product_color"],
                        "product_size": internal["product_size"],
                        "reference_name": internal["reference_name"],
                        "images": _path_value(append, field_map.get("append_images", ""), []),
                        "videos": _path_value(append, field_map.get("append_videos", ""), []),
                    },
                )
            )
    return records
