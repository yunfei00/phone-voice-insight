import json
from pathlib import Path

import pytest

from collectors.base import CollectorError, RawRecord
from collectors.jd.jsonp import parse_json_or_jsonp
from collectors.jd.normalizer import normalize_jd_record
from collectors.jd.parser import parse_comments_payload

FIXTURES = Path(__file__).parent / "fixtures"
FIELD_MAP = {
    "comments": "data.items",
    "comment_id": "commentId",
    "content": "text",
    "rating": "score",
    "creation_time": "createdAt",
    "sku_id": "sku",
    "product_color": "color",
    "product_size": "size",
    "reference_name": "reference",
    "useful_vote_count": "useful",
    "reply_count": "replies",
    "images": "images",
    "videos": "videos",
    "append": "append",
    "append_id": "appendId",
    "append_content": "text",
    "append_time": "createdAt",
    "append_images": "images",
    "append_videos": "videos",
}


def load_records(name: str) -> list[RawRecord]:
    content = (FIXTURES / name).read_text(encoding="utf-8")
    return parse_comments_payload(parse_json_or_jsonp(content), field_map=FIELD_MAP)


def test_main_review_fields_and_privacy_allowlist() -> None:
    record = load_records("comments_page.json")[0]
    normalized = normalize_jd_record(record)
    assert normalized.external_id == "jd_review:900000001"
    assert normalized.record_type == "REVIEW"
    assert normalized.content == "续航表现很好 😊\n系统运行流畅。"
    assert normalized.rating == 5
    assert normalized.published_at is not None
    assert normalized.variant_external_id == "100310496358"
    assert normalized.variant_attributes == {"memory": "12GB", "storage": "512GB", "color": "旭日橙"}
    assert normalized.raw_data["image_count"] == 1
    assert not {"nickname", "uid", "guid", "avatar"}.intersection(normalized.raw_data)


def test_jsonp_fixture_and_multi_variant_mapping() -> None:
    content = (FIXTURES / "comments_page.jsonp").read_text(encoding="utf-8")
    records = parse_comments_payload(
        parse_json_or_jsonp(content, expected_callback="jdCallback"),
        field_map=FIELD_MAP,
    )
    normalized = normalize_jd_record(records[0])
    assert normalized.variant_attributes == {"memory": "12GB", "storage": "256GB", "color": "幻夜黑"}

    variants = [
        normalize_jd_record(record).variant_attributes for record in load_records("comments_multi_variant.json")
    ]
    assert variants == [
        {"memory": "12GB", "storage": "256GB", "color": "旭日橙"},
        {"memory": "12GB", "storage": "512GB", "color": "幻夜黑"},
    ]


def test_append_review_parent_and_media() -> None:
    records = load_records("comments_with_append.json")
    assert len(records) == 2
    append = normalize_jd_record(records[1])
    assert append.external_id == "jd_append:910000003"
    assert append.parent_external_id == "jd_review:900000003"
    assert append.record_type == "APPEND_REVIEW"
    assert append.is_append_review
    assert append.rating is None
    assert append.raw_data["video_count"] == 1


def test_empty_fixture_is_explicitly_empty() -> None:
    payload = json.loads((FIXTURES / "comments_empty.json").read_text(encoding="utf-8"))
    assert parse_comments_payload(payload, field_map=FIELD_MAP) == []


def test_unrelated_identity_fields_never_reach_raw_data() -> None:
    payload = json.loads((FIXTURES / "comments_page.json").read_text(encoding="utf-8"))
    payload["data"]["items"][0].update(
        {"nickname": "should-not-persist", "uid": "private", "guid": "private", "avatar": "https://example.test/a"}
    )
    normalized = normalize_jd_record(parse_comments_payload(payload, field_map=FIELD_MAP)[0])
    serialized = json.dumps(normalized.raw_data, ensure_ascii=False)
    assert "should-not-persist" not in serialized
    assert "private" not in serialized
    assert "example.test" not in serialized


def test_rating_out_of_range_is_not_clamped() -> None:
    payload = json.loads((FIXTURES / "comments_page.json").read_text(encoding="utf-8"))
    payload["data"]["items"][0]["score"] = 6
    normalized = normalize_jd_record(parse_comments_payload(payload, field_map=FIELD_MAP)[0])
    assert normalized.rating is None
    assert "rating_out_of_range" in normalized.raw_data["parse_warnings"]


def test_multiple_append_reviews_without_ids_fail_closed() -> None:
    payload = json.loads((FIXTURES / "comments_page.json").read_text(encoding="utf-8"))
    payload["data"]["items"][0]["append"] = [
        {"text": "第一次追评", "createdAt": "2026-08-03 10:00:00"},
        {"text": "第二次追评", "createdAt": "2026-08-04 10:00:00"},
    ]
    with pytest.raises(CollectorError) as exc_info:
        parse_comments_payload(payload, field_map=FIELD_MAP)
    assert exc_info.value.code == "RESPONSE_FORMAT_CHANGED"
