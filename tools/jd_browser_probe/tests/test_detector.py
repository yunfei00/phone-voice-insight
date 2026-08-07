from tools.jd_browser_probe.detector import (
    build_network_entry,
    inspect_payload,
    is_json_like_content_type,
    parse_json_body,
    query_parameter_schema,
    sensitive_query_names,
)


def test_detector_accepts_jd_json_compatible_content_types() -> None:
    assert is_json_like_content_type("application/json; charset=utf-8")
    assert is_json_like_content_type("text/json")
    assert is_json_like_content_type("text/plain; charset=UTF-8")
    assert not is_json_like_content_type("text/html")


def test_response_schema_detection_uses_url_and_observed_keys() -> None:
    payload = {
        "result": {
            "items": [
                {
                    "commentId": "9001",
                    "content": "续航不错",
                    "score": 5,
                    "creationTime": "2026-08-08 10:00:00",
                    "referenceId": "100310496358",
                    "productColor": "测试颜色",
                }
            ]
        },
        "maxPage": 3,
    }

    result = inspect_payload(payload, url="https://api.m.jd.com/current/comments?productId=100310496358")

    assert result.candidate
    assert result.top_level_keys == ("maxPage", "result")
    assert result.arrays[0].path == "$.result.items"
    assert result.arrays[0].length == 1
    assert {"comment_id", "content", "rating", "time", "sku", "color"}.issubset(result.arrays[0].semantic_hints)
    assert result.sample_items[0]["commentId"] == "9001"
    assert "sample_items" not in result.stage_a_dict()


def test_detector_accepts_json_and_jsonp_without_executing_code() -> None:
    assert parse_json_body('{"comments": []}') == {"comments": []}
    assert parse_json_body('callback({"comments": []});') == {"comments": []}
    assert parse_json_body('alert(1); callback({"comments": []})') is None


def test_network_metadata_redacts_unknown_and_sensitive_query_values() -> None:
    url = "https://api.m.jd.com/comments?productId=100310496358&page=1&h5st=secret-value&unknown=private"
    entry = build_network_entry(
        method="GET",
        url=url,
        status=200,
        content_type="application/json; charset=utf-8",
        resource_type="xhr",
        timestamp="2026-08-08T10:00:00+00:00",
    )

    assert entry is not None
    assert entry["host"] == "api.m.jd.com"
    assert entry["path"] == "/comments"
    assert "productId=100310496358" in entry["url"]
    assert "page=1" in entry["url"]
    assert "secret-value" not in entry["url"]
    assert "private" not in entry["url"]
    assert sensitive_query_names(url) == ("h5st",)
    parameters = query_parameter_schema(url)
    assert next(item for item in parameters if item["name"] == "h5st")["example"] == "<redacted>"
    assert next(item for item in parameters if item["name"] == "unknown")["example"] == "<redacted>"


def test_network_metadata_ignores_non_jd_and_non_xhr_resources() -> None:
    assert (
        build_network_entry(
            method="GET",
            url="https://example.com/comments",
            status=200,
            content_type="application/json",
            resource_type="xhr",
        )
        is None
    )
    assert (
        build_network_entry(
            method="GET",
            url="https://api.m.jd.com/comments",
            status=200,
            content_type="application/json",
            resource_type="image",
        )
        is None
    )
