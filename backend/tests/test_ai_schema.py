import pytest
from ai.schemas.review_analysis import AspectName, ReviewAnalysisOutput
from pydantic import ValidationError


def test_review_analysis_schema_validation() -> None:
    result = ReviewAnalysisOutput.model_validate(
        {
            "product_model": "荣耀 Power2",
            "is_valid_content": True,
            "content_type": "USER_REVIEW",
            "aspects": [
                {
                    "aspect": "BATTERY",
                    "sentiment": "POSITIVE",
                    "sentiment_score": 0.8,
                    "issue_category": "",
                    "issue_summary": "续航体验较好",
                    "evidence_text": "续航能用一整天",
                    "confidence": 0.9,
                }
            ],
            "software_version": None,
            "usage_scenarios": ["日常使用"],
            "summary": "用户认可续航",
            "confidence": 0.9,
            "warnings": [],
        }
    )
    assert result.aspects[0].aspect is AspectName.BATTERY


def test_review_analysis_schema_rejects_invalid_confidence() -> None:
    with pytest.raises(ValidationError):
        ReviewAnalysisOutput.model_validate(
            {
                "product_model": "荣耀 Power2",
                "is_valid_content": False,
                "content_type": "OTHER",
                "aspects": [],
                "usage_scenarios": [],
                "summary": "",
                "confidence": 1.5,
                "warnings": [],
            }
        )
