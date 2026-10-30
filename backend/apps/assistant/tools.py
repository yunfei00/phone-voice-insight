from __future__ import annotations

import json
from collections.abc import Callable
from datetime import date
from typing import Any, Literal

from django.core.serializers.json import DjangoJSONEncoder
from django.db.models import Q
from django.utils import timezone
from pydantic import BaseModel, ConfigDict, Field, model_validator

from apps.analysis.models import OpinionAspect
from apps.products.models import Product
from apps.reports import services as report_services
from apps.reviews.services.final_corpus import final_corpus_reviews


class ToolInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    product_id: int | None = Field(default=None, ge=1)
    source_id: int | None = Field(default=None, ge=1)
    start_date: date | None = None
    end_date: date | None = None

    @model_validator(mode="after")
    def validate_dates(self) -> ToolInput:
        if self.start_date and self.end_date and self.start_date > self.end_date:
            raise ValueError("开始日期不能晚于结束日期")
        return self


class ProductOverviewInput(ToolInput):
    pass


class IssueStatisticsInput(ToolInput):
    category: str | None = Field(default=None, max_length=80)
    severity: str | None = Field(default=None, max_length=20)
    limit: int = Field(default=10, ge=1, le=50)


class CompareProductsInput(ToolInput):
    product_ids: list[int] = Field(min_length=2, max_length=5)


class SearchFeedbackInput(ToolInput):
    keyword: str = Field(min_length=1, max_length=120)
    category: str | None = Field(default=None, max_length=80)
    limit: int = Field(default=10, ge=1, le=30)


class IssueEvidenceInput(ToolInput):
    issue_id: str = Field(min_length=3, max_length=180)
    limit: int = Field(default=10, ge=1, le=20)


class FeedbackTrendsInput(ToolInput):
    granularity: Literal["day"] = "day"


TOOL_MODELS: dict[str, type[BaseModel]] = {
    "get_product_overview": ProductOverviewInput,
    "get_issue_statistics": IssueStatisticsInput,
    "compare_products": CompareProductsInput,
    "search_feedback": SearchFeedbackInput,
    "get_issue_evidence": IssueEvidenceInput,
    "get_feedback_trends": FeedbackTrendsInput,
}

TOOL_DESCRIPTIONS = {
    "get_product_overview": "查询产品反馈总量、有效反馈量、AI 分析量和明确问题量。",
    "get_issue_statistics": "按产品、来源、时间、分类和严重程度统计明确用户问题。",
    "compare_products": "比较两个至五个产品的问题数量、分类比例和样本可信度。",
    "search_feedback": "在最终有效 AI 语料中检索真实用户反馈。",
    "get_issue_evidence": "获取指定问题的真实原始证据和来源链接。",
    "get_feedback_trends": "查询指定范围内有效反馈和明确问题的按日趋势。",
}


def _params(value: ToolInput) -> dict[str, Any]:
    return {key: item for key, item in value.model_dump().items() if item not in (None, "")}


def _json_safe(value: Any) -> Any:
    return json.loads(json.dumps(value, cls=DjangoJSONEncoder))


def _meta(params: dict[str, Any], sample_size: int) -> dict[str, Any]:
    _, _, start_day, end_day = report_services.parse_range(params)
    return {
        "start_date": start_day,
        "end_date": end_day,
        "sample_size": sample_size,
        "data_cutoff": timezone.now(),
        "scope_note": "仅统计通过治理与结构化校验的最终有效 AI 语料。",
    }


def get_product_overview(value: ProductOverviewInput) -> dict[str, Any]:
    params = _params(value)
    result = report_services.overview(params)
    return _json_safe({"overview": result, "meta": _meta(params, result["ai_analyzed"])})


def get_issue_statistics(value: IssueStatisticsInput) -> dict[str, Any]:
    params = _params(value)
    limit = int(params.pop("limit", 10))
    rows = report_services.issue_rows(params)
    category = str(params.get("category") or "").strip().upper()
    severity = str(params.get("severity") or "").strip().upper()
    if category:
        rows = [row for row in rows if str(row["category"]).upper() == category]
    if severity:
        rows = [row for row in rows if str(row["severity"]).upper() == severity]
    rows = rows[:limit]
    sample_size = sum(int(row["feedback_count"]) for row in rows)
    return _json_safe(
        {"issues": rows, "categories": report_services.categories(params), "meta": _meta(params, sample_size)}
    )


def compare_products(value: CompareProductsInput) -> dict[str, Any]:
    params = _params(value)
    product_ids = list(dict.fromkeys(params.pop("product_ids")))
    products = {item.id: item for item in Product.objects.filter(id__in=product_ids, is_active=True)}
    if len(products) != len(product_ids):
        raise ValueError("一个或多个产品不存在或已停用")
    rows = []
    for product_id in product_ids:
        scoped = {**params, "product_id": product_id}
        overview = report_services.overview(scoped)
        rows.append(
            {
                "product_id": product_id,
                "product_name": products[product_id].name,
                "overview": overview,
                "categories": report_services.categories(scoped),
                "top_issues": report_services.issue_rows(scoped)[:5],
                "negative_ratio": (
                    round(overview["explicit_issue_feedback"] / overview["ai_analyzed"], 4)
                    if overview["ai_analyzed"]
                    else None
                ),
                "ratio_denominator": overview["ai_analyzed"],
            }
        )
    return _json_safe({"products": rows, "meta": _meta(params, sum(row["overview"]["ai_analyzed"] for row in rows))})


def search_feedback(value: SearchFeedbackInput) -> dict[str, Any]:
    params = _params(value)
    keyword = str(params.pop("keyword"))
    category = str(params.pop("category", "")).upper()
    limit = int(params.pop("limit", 10))
    queryset = final_corpus_reviews().select_related("product", "source")
    start, end, _, _ = report_services.parse_range(params)
    queryset = queryset.filter(
        Q(published_at__gte=start, published_at__lt=end)
        | Q(published_at__isnull=True, collected_at__gte=start, collected_at__lt=end)
    )
    if product_id := params.get("product_id"):
        queryset = queryset.filter(product_id=product_id)
    if source_id := params.get("source_id"):
        queryset = queryset.filter(source_id=source_id)
    queryset = queryset.filter(Q(title__icontains=keyword) | Q(content__icontains=keyword))
    if category:
        content_ids = OpinionAspect.objects.filter(
            analysis__content_id__in=queryset.values("id"), aspect_code=category
        ).values("analysis__content_id")
        queryset = queryset.filter(id__in=content_ids)
    rows = list(
        queryset.values(
            "id",
            "product_id",
            "product__name",
            "source__name",
            "title",
            "content",
            "source_url",
            "published_at",
            "collected_at",
        ).order_by("-published_at", "-collected_at")[:limit]
    )
    for row in rows:
        row["content"] = str(row["content"])[:800]
    return _json_safe({"feedback": rows, "meta": _meta(params, len(rows)), "keyword": keyword})


def get_issue_evidence(value: IssueEvidenceInput) -> dict[str, Any]:
    params = _params(value)
    issue_id = str(params.pop("issue_id"))
    limit = int(params.pop("limit", 10))
    detail = report_services.issue_detail(issue_id, params)
    detail["evidence"] = detail["evidence"][:limit]
    return _json_safe({"issue": detail, "meta": _meta(params, len(detail["evidence"]))})


def get_feedback_trends(value: FeedbackTrendsInput) -> dict[str, Any]:
    params = _params(value)
    params.pop("granularity", None)
    rows = report_services.trends(params)
    return _json_safe({"trends": rows, "meta": _meta(params, sum(row["valid_feedback"] for row in rows))})


TOOL_HANDLERS: dict[str, Callable[[Any], dict[str, Any]]] = {
    "get_product_overview": get_product_overview,
    "get_issue_statistics": get_issue_statistics,
    "compare_products": compare_products,
    "search_feedback": search_feedback,
    "get_issue_evidence": get_issue_evidence,
    "get_feedback_trends": get_feedback_trends,
}


def tool_specs() -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": name,
                "description": TOOL_DESCRIPTIONS[name],
                "parameters": model.model_json_schema(),
            },
        }
        for name, model in TOOL_MODELS.items()
    ]


def execute_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    model = TOOL_MODELS.get(name)
    handler = TOOL_HANDLERS.get(name)
    if model is None or handler is None:
        raise ValueError("不支持的业务工具")
    arguments = dict(arguments)
    if (
        "limit" in model.model_fields
        and isinstance(arguments.get("limit"), (int, float))
        and not isinstance(arguments["limit"], bool)
    ):
        arguments["limit"] = max(
            1,
            min(
                int(arguments["limit"]),
                50 if name == "get_issue_statistics" else 30 if name == "search_feedback" else 20,
            ),
        )
    validated = model.model_validate(arguments)
    return handler(validated)
