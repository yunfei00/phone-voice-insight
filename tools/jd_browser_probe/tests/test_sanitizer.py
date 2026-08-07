import json

from tools.jd_browser_probe.sanitizer import find_denied_keys, sanitize_value


def test_sanitizer_recursively_removes_user_identity_and_secret_fields() -> None:
    raw = {
        "commentId": "9001",
        "content": "联系 test@example.com 或 13800138000",
        "nickName": "private-name",
        "nested": {
            "uid": "private-uid",
            "guid": "private-guid",
            "avatar": "https://example.test/avatar.png",
            "userPin": "private-pin",
            "score": 5,
        },
        "items": [{"phone": "13800138000", "referenceId": "100310496358"}],
    }

    sanitized = sanitize_value(raw)
    serialized = json.dumps(sanitized, ensure_ascii=False)

    assert sanitized["commentId"] == "9001"
    assert sanitized["nested"]["score"] == 5
    assert sanitized["items"][0]["referenceId"] == "100310496358"
    assert find_denied_keys(sanitized) == []
    for secret in (
        "private-name",
        "private-uid",
        "private-guid",
        "private-pin",
        "test@example.com",
        "13800138000",
        "example.test",
    ):
        assert secret not in serialized
