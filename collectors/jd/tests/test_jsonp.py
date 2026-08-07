import pytest

from collectors.base import CollectorError
from collectors.jd.jsonp import parse_json_or_jsonp


def test_parses_json_and_jsonp() -> None:
    assert parse_json_or_jsonp('{"ok": true}') == {"ok": True}
    assert parse_json_or_jsonp('cb_1({"ok": true});', expected_callback="cb_1") == {"ok": True}


@pytest.mark.parametrize(
    "content,callback",
    [
        ('wrong({"ok": true})', "expected"),
        ('alert(1); cb({"ok": true})', None),
        ("cb({bad json})", "cb"),
    ],
)
def test_rejects_invalid_or_malicious_jsonp(content: str, callback: str | None) -> None:
    with pytest.raises(CollectorError) as exc_info:
        parse_json_or_jsonp(content, expected_callback=callback)
    assert exc_info.value.code == "RESPONSE_FORMAT_CHANGED"
