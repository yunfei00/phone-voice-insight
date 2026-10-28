import copy
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from ai.schemas.structured_analysis import StructuredAnalysisPayload
from ai.taxonomy import load_taxonomy, validate_tag_relation
from ai.validation import validate_structured_payload
from pydantic import ValidationError


def valid_payload() -> dict[str, Any]:
    return {
        "schema_version": "1.0.0",
        "taxonomy_version": "1.0.0",
        "overall_sentiment": "NEGATIVE",
        "language": "zh-CN",
        "content_type": "COMMUNITY_REPLY",
        "relevance": "RELEVANT",
        "summary": "用户反馈地下车库信号不稳定",
        "model_mentions": ["荣耀 Power2"],
        "aspects": [{
            "business_domains": ["NET"], "aspect_code": "NET", "topic_code": "NET.CELLULAR",
            "sentiment": "NEGATIVE", "intent": "COMPLAINT", "issue_type": "RELIABILITY",
            "severity": "MEDIUM", "scenario": "地下车库", "trigger": None, "phenomenon": "信号不稳定",
            "target_product": "荣耀 Power2", "compared_products": [], "relation_type": "SELF",
            "evidence_text": "地下车库信号不稳定", "evidence_start": 0, "evidence_end": 10,
            "confidence": 0.93, "review_required": False,
        }],
    }


def test_taxonomy_is_versioned_and_has_fifteen_domains() -> None:
    taxonomy = load_taxonomy()
    assert taxonomy.taxonomy_version == "1.0.0"
    assert len(taxonomy.domains) == 15
    assert validate_tag_relation("NET", "NET.CELLULAR")


@pytest.mark.parametrize(
    ("mutation", "valid"),
    [
        (lambda p: p, True),
        (lambda p: p.update(aspects=[]), True),
        (lambda p: p.update(overall_sentiment="MIXED"), True),
        (lambda p: p.update(relevance="IRRELEVANT", aspects=[]), True),
        (lambda p: p.update(schema_version="2.0.0"), False),
        (lambda p: p.update(taxonomy_version="2.0.0"), False),
        (lambda p: p.update(overall_sentiment="BAD"), False),
        (lambda p: p.update(language=""), False),
        (lambda p: p.update(content_type="POST"), False),
        (lambda p: p.update(relevance="YES"), False),
        (lambda p: p.update(extra="x"), False),
        (lambda p: p["aspects"][0].update(aspect_code="NOPE"), False),
        (lambda p: p["aspects"][0].update(topic_code="BAT.BATTERY_LIFE"), False),
        (lambda p: p["aspects"][0].update(business_domains=["BAT"]), False),
        (lambda p: p["aspects"][0].update(sentiment="BAD"), False),
        (lambda p: p["aspects"][0].update(intent="BUY_NOW"), False),
        (lambda p: p["aspects"][0].update(issue_type="BUGGY"), False),
        (lambda p: p["aspects"][0].update(severity="P0"), False),
        (lambda p: p["aspects"][0].update(confidence=1.1), False),
        (lambda p: p["aspects"][0].update(evidence_start=-1), False),
        (lambda p: p["aspects"][0].update(evidence_end=0), False),
        (lambda p: p["aspects"][0].update(unknown=True), False),
    ],
)
def test_schema_positive_and_negative_cases(
    mutation: Callable[[dict[str, Any]], object], valid: bool
) -> None:
    payload = copy.deepcopy(valid_payload())
    mutation(payload)
    if valid:
        StructuredAnalysisPayload.model_validate(payload)
    else:
        with pytest.raises(ValidationError):
            StructuredAnalysisPayload.model_validate(payload)


def test_evidence_offsets_use_python_unicode_code_points() -> None:
    source = "地下车库信号不稳定"
    result = validate_structured_payload(valid_payload(), source)
    assert result.valid
    assert result.payload is not None


def test_evidence_mismatch_is_rejected() -> None:
    payload = valid_payload()
    payload["aspects"][0]["evidence_start"] = 1
    result = validate_structured_payload(payload, "地下车库信号不稳定")
    assert not result.valid
    assert "offset mismatch" in result.errors[0]


def test_target_product_must_be_declared() -> None:
    payload = valid_payload()
    payload["model_mentions"] = []
    assert not validate_structured_payload(payload, "地下车库信号不稳定").valid


def test_personal_information_is_rejected_from_summary() -> None:
    payload = valid_payload()
    payload["summary"] = "请联系 13800138000"
    assert not validate_structured_payload(payload, "地下车库信号不稳定").valid


def test_json_schema_declares_draft_2020_12() -> None:
    path = Path(__file__).parents[2] / "schemas" / "structured_analysis_v1.schema.json"
    schema = json.loads(path.read_text(encoding="utf-8"))
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert schema["additionalProperties"] is False

