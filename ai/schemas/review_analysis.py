"""结构化分析和聚类的数据契约。"""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class StrictSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AspectName(StrEnum):
    BATTERY = "BATTERY"
    CHARGING = "CHARGING"
    HEATING = "HEATING"
    SIGNAL = "SIGNAL"
    PERFORMANCE = "PERFORMANCE"
    SYSTEM_FLUENCY = "SYSTEM_FLUENCY"
    SYSTEM_BUG = "SYSTEM_BUG"
    DISPLAY = "DISPLAY"
    CAMERA = "CAMERA"
    WEIGHT_AND_FEEL = "WEIGHT_AND_FEEL"
    BUILD_QUALITY = "BUILD_QUALITY"
    AUDIO_AND_CALL = "AUDIO_AND_CALL"
    DURABILITY = "DURABILITY"
    VALUE_FOR_MONEY = "VALUE_FOR_MONEY"
    AFTER_SALES = "AFTER_SALES"


class SentimentName(StrEnum):
    POSITIVE = "POSITIVE"
    NEUTRAL = "NEUTRAL"
    NEGATIVE = "NEGATIVE"
    MIXED = "MIXED"


class ContentType(StrEnum):
    USER_REVIEW = "USER_REVIEW"
    COMMUNITY_THREAD = "COMMUNITY_THREAD"
    COMMUNITY_REPLY = "COMMUNITY_REPLY"
    LOGISTICS_OR_SERVICE = "LOGISTICS_OR_SERVICE"
    OFFICIAL_REPLY = "OFFICIAL_REPLY"
    OTHER = "OTHER"


class ReviewAnalysisInput(StrictSchema):
    review_id: str
    product_model: str
    content: str = Field(min_length=1)
    title: str | None = None
    source: str
    record_type: str
    is_official: bool = False
    rating: float | None = Field(default=None, ge=0, le=5)
    software_version: str | None = None


class EvidenceReference(StrictSchema):
    review_id: str
    evidence_text: str = Field(min_length=1)


class AspectAnalysisItem(StrictSchema):
    aspect: AspectName
    sentiment: SentimentName
    sentiment_score: float | None = Field(default=None, ge=-1, le=1)
    issue_category: str = ""
    issue_summary: str = ""
    evidence_text: str = Field(min_length=1)
    confidence: float = Field(ge=0, le=1)


class ReviewAnalysisOutput(StrictSchema):
    product_model: str
    is_valid_content: bool
    content_type: ContentType
    aspects: list[AspectAnalysisItem]
    software_version: str | None = None
    usage_scenarios: list[str]
    summary: str
    confidence: float = Field(ge=0, le=1)
    warnings: list[str]


class IssueClusterInput(StrictSchema):
    product_model: str
    aspect: AspectName
    items: list[EvidenceReference]


class IssueClusterOutput(StrictSchema):
    cluster_id: str
    title: str
    aspect: AspectName
    issue_category: str
    evidence: list[EvidenceReference]
    confidence: float = Field(ge=0, le=1)
