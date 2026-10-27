"""AI 结构化分析 V1 的强类型输出契约。"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ai.taxonomy import TAXONOMY_VERSION, validate_tag_relation

SCHEMA_VERSION = "1.0.0"

Sentiment = Literal["POSITIVE", "NEUTRAL", "NEGATIVE", "MIXED", "UNKNOWN"]
Intent = Literal[
    "EXPERIENCE", "COMPLAINT", "PRAISE", "QUESTION", "SUGGESTION", "COMPARISON",
    "PURCHASE_INTENT", "SERVICE_REQUEST", "OTHER", "UNKNOWN",
]
IssueType = Literal[
    "QUALITY", "PERFORMANCE", "USABILITY", "COMPATIBILITY", "RELIABILITY", "PRIVACY",
    "SERVICE", "PRICE", "REQUIREMENT", "OTHER", "UNKNOWN",
]
Severity = Literal["CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO", "UNKNOWN"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class OpinionAspectPayload(StrictModel):
    business_domains: list[str] = Field(min_length=1)
    aspect_code: str
    topic_code: str
    sentiment: Sentiment
    intent: Intent
    issue_type: IssueType
    severity: Severity
    scenario: str | None = None
    trigger: str | None = None
    phenomenon: str | None = None
    target_product: str | None = None
    compared_products: list[str] = Field(default_factory=list)
    relation_type: Literal["SELF", "COMPARED_WITH", "MENTION_ONLY", "UNKNOWN"]
    evidence_text: str = Field(min_length=1)
    evidence_start: int = Field(ge=0)
    evidence_end: int = Field(gt=0)
    confidence: float = Field(ge=0, le=1)
    review_required: bool = False

    @model_validator(mode="after")
    def validate_taxonomy(self) -> "OpinionAspectPayload":
        if self.aspect_code not in self.business_domains:
            raise ValueError("aspect_code must be included in business_domains")
        if not validate_tag_relation(self.aspect_code, self.topic_code):
            raise ValueError("topic_code does not belong to aspect_code")
        if self.evidence_end <= self.evidence_start:
            raise ValueError("evidence_end must be greater than evidence_start")
        return self


class StructuredAnalysisPayload(StrictModel):
    schema_version: Literal["1.0.0"] = SCHEMA_VERSION
    taxonomy_version: Literal["1.0.0"] = TAXONOMY_VERSION
    overall_sentiment: Sentiment
    language: str = Field(min_length=2, max_length=20)
    content_type: Literal[
        "USER_REVIEW", "COMMUNITY_THREAD", "COMMUNITY_REPLY", "OFFICIAL_REPLY", "LOGISTICS_OR_SERVICE",
        "OTHER",
    ]
    relevance: Literal["RELEVANT", "PARTIAL", "IRRELEVANT", "UNKNOWN"]
    summary: str = Field(max_length=500)
    model_mentions: list[str] = Field(default_factory=list)
    aspects: list[OpinionAspectPayload] = Field(default_factory=list)

