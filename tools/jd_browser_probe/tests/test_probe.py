import json
from pathlib import Path

from tools.jd_browser_probe.detector import inspect_payload
from tools.jd_browser_probe.probe import (
    CandidateCapture,
    ProbeRecorder,
    _finalize_reports,
    classify_result,
    live_probe_enabled,
)
from tools.jd_browser_probe.sanitizer import find_denied_keys


def make_candidate() -> CandidateCapture:
    url = "https://api.m.jd.com/comments?productId=100310496358&page=1"
    detection = inspect_payload(
        {
            "comments": [
                {
                    "commentId": "9001",
                    "content": "真实结构样例",
                    "score": 5,
                    "creationTime": "2026-08-08 10:00:00",
                    "referenceId": "100310496358",
                    "nickName": "must-disappear",
                    "uid": "must-disappear",
                    "guid": "must-disappear",
                    "avatar": "https://example.test/private.png",
                }
            ]
        },
        url=url,
    )
    return CandidateCapture(
        candidate_id=1,
        network={
            "timestamp": "2026-08-08T10:00:00+00:00",
            "method": "GET",
            "url": url,
            "host": "api.m.jd.com",
            "path": "/comments",
            "status": 200,
            "content_type": "application/json",
            "resource_type": "xhr",
        },
        detection=detection,
        query_parameters=[
            {"name": "productId", "example": "100310496358", "meaning": "未确认"},
            {"name": "page", "example": "1", "meaning": "未确认"},
        ],
        sensitive_parameter_names=(),
    )


def test_result_classification() -> None:
    candidate = make_candidate()
    assert (
        classify_result(selected=candidate, review_area_normal=True, login_required=False) == "A PUBLIC_ENDPOINT_FOUND"
    )
    assert (
        classify_result(selected=candidate, review_area_normal=True, login_required=True)
        == "B BROWSER_SESSION_REQUIRED"
    )
    assert (
        classify_result(selected=None, review_area_normal=False, login_required=False) == "C JD_REVIEW_ACCESS_BLOCKED"
    )


def test_sanitized_sample_contains_no_user_identifiers(tmp_path: Path) -> None:
    output_dir = tmp_path / ".local" / "jd-probe"
    docs_path = tmp_path / "docs" / "jd-interface-discovery.md"
    docs_path.parent.mkdir(parents=True)
    recorder = ProbeRecorder(output_dir=output_dir)
    candidate = make_candidate()
    recorder.candidates.append(candidate)

    report = _finalize_reports(
        output_dir=output_dir,
        docs_path=docs_path,
        recorder=recorder,
        selected=candidate,
        product={"product_id": "100310496358", "product_name": "荣耀 Power2", "shop": "测试店铺"},
        access={
            "product_page_normal": True,
            "review_area_normal": True,
            "login_required": False,
            "captcha_seen": False,
            "risk_seen": False,
            "login_page_seen": False,
        },
    )

    sample = json.loads((output_dir / "sanitized-sample.json").read_text(encoding="utf-8"))
    serialized = json.dumps(sample, ensure_ascii=False).casefold()
    assert find_denied_keys(sample) == []
    for forbidden in ("nickname", "uid", "guid", "avatar", "pin", "phone", "email", "must-disappear"):
        assert forbidden not in serialized
    assert report["privacy"]["cookies_saved"] is False
    assert report["privacy"]["authorization_saved"] is False
    assert "must-disappear" not in docs_path.read_text(encoding="utf-8")


def test_live_probe_is_disabled_by_default(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.delenv("RUN_JD_BROWSER_LIVE_TEST", raising=False)
    assert not live_probe_enabled()
