import pytest

from apps.reviews.services.ai_governance import validate_ai_governance_response


def test_valid_ai_governance_response():
    payload = validate_ai_governance_response(
        '{"eligible":true,"confidence":0.92,"reason":"有明确耗电反馈","evidence":"耗电很快"}',
        "升级后耗电很快",
    )
    assert payload["eligible"] is True
    assert payload["evidence"] == "耗电很快"


@pytest.mark.parametrize("response", [
    '{"eligible":"true","confidence":0.9,"reason":"测试","evidence":""}',
    '{"eligible":true,"confidence":1.2,"reason":"测试","evidence":""}',
    '{"eligible":true,"confidence":0.8,"reason":"测试","evidence":"编造证据"}',
    '{"eligible":true,"confidence":0.8,"reason":"","evidence":""}',
    '{"eligible":true,"confidence":0.8,"reason":"测试","evidence":"","extra":"x"}',
    "not json",
])
def test_invalid_ai_governance_response_is_rejected(response):
    with pytest.raises((ValueError, TypeError)):
        validate_ai_governance_response(response, "升级后耗电很快")
