"""驾驶舱统一统计口径与确定性报告生成。"""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import date, datetime, time, timedelta
from typing import Any

from ai.taxonomy import load_taxonomy
from django.conf import settings
from django.core.serializers.json import DjangoJSONEncoder
from django.db import transaction
from django.db.models import Case, Count, DateTimeField, F, Max, Min, Q, QuerySet, Value, When
from django.db.models.functions import Coalesce, Lower, Replace, TruncDate
from django.utils import timezone

from apps.analysis.models import AnalysisRun, OpinionAspect, StructuredAnalysis, StructuredRunStatus
from apps.products.models import Product
from apps.reports.models import AggregateReport, ReportStatus, ReportType
from apps.reviews.models import ReviewQuality, ReviewRecord
from apps.reviews.services.final_corpus import final_corpus_reviews
from apps.sources.models import DataSource

SEVERITY_RANK = {"UNKNOWN": 0, "INFO": 1, "LOW": 2, "MEDIUM": 3, "HIGH": 4, "CRITICAL": 5}
SEVERITY_BY_RANK = {value: key for key, value in SEVERITY_RANK.items()}


def taxonomy_labels() -> tuple[dict[str, str], dict[str, str]]:
    taxonomy = load_taxonomy()
    domains = {domain.tag_id: domain.name for domain in taxonomy.domains if domain.enabled}
    topics = {
        child.tag_id: child.name
        for domain in taxonomy.domains
        if domain.enabled
        for child in domain.children
        if child.enabled
    }
    return domains, topics


def parse_range(params: Mapping[str, Any]) -> tuple[datetime, datetime, date, date]:
    today = timezone.localdate()
    try:
        start_day = date.fromisoformat(str(params.get("start_date") or today - timedelta(days=29)))
        end_day = date.fromisoformat(str(params.get("end_date") or today))
    except ValueError as exc:
        raise ValueError("日期格式必须为 YYYY-MM-DD") from exc
    if start_day > end_day:
        raise ValueError("开始日期不能晚于结束日期")
    current_timezone = timezone.get_current_timezone()
    start = timezone.make_aware(datetime.combine(start_day, time.min), current_timezone)
    end = timezone.make_aware(datetime.combine(end_day + timedelta(days=1), time.min), current_timezone)
    return start, end, start_day, end_day


def _integer(params: Mapping[str, Any], name: str) -> int | None:
    value = params.get(name)
    if value in (None, ""):
        return None
    try:
        return int(str(value))
    except ValueError as exc:
        raise ValueError(f"{name} 必须为整数") from exc


def filtered_reviews(params: Mapping[str, Any]) -> QuerySet[ReviewRecord]:
    start, end, _, _ = parse_range(params)
    queryset = ReviewRecord.objects.annotate(
        metric_time=Coalesce("published_at", "collected_at", output_field=DateTimeField())
    ).filter(metric_time__gte=start, metric_time__lt=end)
    if product_id := _integer(params, "product_id"):
        queryset = queryset.filter(product_id=product_id)
    if source_id := _integer(params, "source_id"):
        queryset = queryset.filter(source_id=source_id)
    return queryset


def valid_qualities(params: Mapping[str, Any]) -> QuerySet[ReviewQuality]:
    return ReviewQuality.objects.filter(
        review_id__in=filtered_reviews(params).values("id"),
        eligible_for_ai=True,
        is_official_content=False,
    )


def accepted_analyses(params: Mapping[str, Any]) -> QuerySet[StructuredAnalysis]:
    return StructuredAnalysis.objects.filter(
        content_id__in=filtered_reviews(params).values("id"),
        content__quality__eligible_for_ai=True,
        content__quality__is_official_content=False,
        content_id__in=final_corpus_reviews().values("pk"),
        run__is_current=True,
        run__status__in=(StructuredRunStatus.SUCCEEDED, StructuredRunStatus.REVIEW_REQUIRED),
        schema_valid=True,
        review_required=False,
    ).distinct()


def issue_aspects(params: Mapping[str, Any]) -> QuerySet[OpinionAspect]:
    queryset = (
        OpinionAspect.objects.annotate(
            normalized_target_product=Replace(
                Replace(Lower(Coalesce("target_product", Value(""))), Value(" "), Value("")),
                Value("　"),
                Value(""),
            ),
            normalized_content_product=Replace(
                Replace(Lower("analysis__content__product__name"), Value(" "), Value("")),
                Value("　"),
                Value(""),
            ),
        )
        .filter(
            analysis_id__in=accepted_analyses(params).values("id"),
            sentiment="NEGATIVE",
        )
        .filter(
            Q(target_product__isnull=True)
            | Q(target_product="")
            | Q(normalized_target_product=F("normalized_content_product"))
        )
    )
    if category := params.get("category"):
        queryset = queryset.filter(aspect_code=str(category))
    if topic := params.get("topic"):
        queryset = queryset.filter(topic_code=str(topic))
    if severity := params.get("severity"):
        queryset = queryset.filter(severity=str(severity))
    search = str(params.get("search") or "").strip()
    if search:
        _, topics = taxonomy_labels()
        matching_topics = [code for code, name in topics.items() if search.lower() in name.lower()]
        queryset = queryset.filter(
            Q(topic_code__in=matching_topics)
            | Q(phenomenon__icontains=search)
            | Q(evidence_text__icontains=search)
            | Q(analysis__summary__icontains=search)
        )
    return queryset


def _severity_annotation() -> Case:
    return Case(
        *(When(severity=name, then=Value(rank)) for name, rank in SEVERITY_RANK.items()),
        default=Value(0),
    )


def issue_rows(params: Mapping[str, Any]) -> list[dict[str, Any]]:
    _, topic_labels = taxonomy_labels()
    start, end, _, _ = parse_range(params)
    seven_days_ago = end - timedelta(days=7)
    previous_start = seven_days_ago - timedelta(days=7)
    grouped = list(
        issue_aspects(params)
        .annotate(metric_time=Coalesce("analysis__content__published_at", "analysis__content__collected_at"))
        .values("analysis__content__product_id", "analysis__content__product__name", "aspect_code", "topic_code")
        .annotate(
            feedback_count=Count("analysis__content_id", distinct=True),
            recent_count=Count(
                "analysis__content_id",
                filter=Q(
                    metric_time__gte=seven_days_ago,
                    metric_time__lt=end,
                ),
                distinct=True,
            ),
            previous_count=Count(
                "analysis__content_id",
                filter=Q(
                    metric_time__gte=previous_start,
                    metric_time__lt=seven_days_ago,
                ),
                distinct=True,
            ),
            severity_rank=Max(_severity_annotation()),
            first_seen=Min(Coalesce("analysis__content__published_at", "analysis__content__collected_at")),
            last_seen=Max(Coalesce("analysis__content__published_at", "analysis__content__collected_at")),
        )
    )
    result: list[dict[str, Any]] = []
    for row in grouped:
        current = int(row["recent_count"])
        previous = int(row["previous_count"])
        growth = None if previous == 0 else round((current - previous) / previous * 100, 1)
        is_new = previous == 0 and current > 0
        product_id = int(row["analysis__content__product_id"])
        topic_code = str(row["topic_code"])
        result.append(
            {
                "id": f"{product_id}:{topic_code}",
                "product_id": product_id,
                "product_name": row["analysis__content__product__name"],
                "category": row["aspect_code"],
                "topic_code": topic_code,
                "name": topic_labels.get(topic_code, topic_code),
                "feedback_count": row["feedback_count"],
                "recent_count": current,
                "previous_count": previous,
                "growth_rate": growth,
                "is_new": is_new,
                "severity": SEVERITY_BY_RANK.get(int(row["severity_rank"] or 0), "UNKNOWN"),
                "first_seen": row["first_seen"],
                "last_seen": row["last_seen"],
                "range_start": start,
            }
        )
    ordering = str(params.get("ordering") or "-feedback_count")
    reverse = ordering.startswith("-")
    key = ordering.lstrip("-")
    allowed = {"feedback_count", "recent_count", "last_seen", "severity"}
    if key not in allowed:
        key = "feedback_count"
        reverse = True
    if key == "severity":
        result.sort(key=lambda item: SEVERITY_RANK.get(str(item[key]), 0), reverse=reverse)
    elif key == "last_seen":
        result.sort(key=lambda item: item[key] or start, reverse=reverse)
    else:
        result.sort(key=lambda item: item[key] or 0, reverse=reverse)
    return result


def watchlist(params: Mapping[str, Any]) -> list[dict[str, Any]]:
    minimum = settings.DASHBOARD_WATCH_MIN_COUNT
    growth_threshold = settings.DASHBOARD_WATCH_GROWTH_PERCENT
    watched = []
    for row in issue_rows(params):
        enough = row["recent_count"] >= minimum
        growing = row["is_new"] or (row["growth_rate"] is not None and row["growth_rate"] >= growth_threshold)
        if enough and growing:
            watched.append(row)
    return watched[:5]


def overview(params: Mapping[str, Any]) -> dict[str, Any]:
    reviews = filtered_reviews(params)
    valid = valid_qualities(params)
    analyses = accepted_analyses(params)
    aspects = issue_aspects(params)
    latest = reviews.aggregate(value=Max("collected_at"))["value"]
    _, _, start_day, end_day = parse_range(params)
    return {
        "filters": {"start_date": start_day, "end_date": end_day},
        "raw_feedback": reviews.count(),
        "valid_feedback": valid.values("review_id").distinct().count(),
        "ai_analyzed": analyses.values("content_id").distinct().count(),
        "explicit_issue_feedback": aspects.values("analysis__content_id").distinct().count(),
        "watch_issue_count": len(watchlist(params)),
        "latest_data_at": latest,
        "published_time_fallback_count": reviews.filter(published_at__isnull=True).count(),
        "disclaimer": "论坛明确负面反馈占比不等于真实设备故障率, 未分析数据不会被视为无问题。",
    }


def trends(params: Mapping[str, Any]) -> list[dict[str, Any]]:
    valid = (
        valid_qualities(params)
        .annotate(day=TruncDate(Coalesce("review__published_at", "review__collected_at")))
        .values("day")
        .annotate(count=Count("review_id", distinct=True))
    )
    issues = (
        issue_aspects(params)
        .annotate(day=TruncDate(Coalesce("analysis__content__published_at", "analysis__content__collected_at")))
        .values("day")
        .annotate(count=Count("analysis__content_id", distinct=True))
    )
    valid_map = {row["day"]: row["count"] for row in valid}
    issue_map = {row["day"]: row["count"] for row in issues}
    start, end, _, _ = parse_range(params)
    cursor = timezone.localtime(start).date()
    final = timezone.localtime(end - timedelta(microseconds=1)).date()
    rows = []
    while cursor <= final:
        rows.append(
            {"date": cursor, "valid_feedback": valid_map.get(cursor, 0), "explicit_issues": issue_map.get(cursor, 0)}
        )
        cursor += timedelta(days=1)
    return rows


def categories(params: Mapping[str, Any]) -> list[dict[str, Any]]:
    domain_labels, _ = taxonomy_labels()
    denominator = accepted_analyses(params).values("content_id").distinct().count()
    rows = (
        issue_aspects(params)
        .values("aspect_code")
        .annotate(feedback_count=Count("analysis__content_id", distinct=True))
        .order_by("-feedback_count")[:10]
    )
    return [
        {
            "code": row["aspect_code"],
            "name": domain_labels.get(row["aspect_code"], row["aspect_code"]),
            "feedback_count": row["feedback_count"],
            "analyzed_denominator": denominator,
            "ratio": round(row["feedback_count"] / denominator, 4) if denominator else None,
        }
        for row in rows
    ]


def product_summaries(params: Mapping[str, Any]) -> list[dict[str, Any]]:
    products = Product.objects.filter(is_active=True).order_by("name")
    if product_id := _integer(params, "product_id"):
        products = products.filter(pk=product_id)
    product_rows = list(products)
    product_ids = [item.id for item in product_rows]
    if not product_ids:
        return []

    review_stats = {
        row["product_id"]: row
        for row in filtered_reviews(params)
        .filter(product_id__in=product_ids)
        .values("product_id")
        .annotate(latest_data_at=Max("collected_at"))
    }
    valid_counts = {
        row["review__product_id"]: row["count"]
        for row in valid_qualities(params)
        .filter(review__product_id__in=product_ids)
        .values("review__product_id")
        .annotate(count=Count("review_id", distinct=True))
    }
    analyzed_counts = {
        row["content__product_id"]: row["count"]
        for row in accepted_analyses(params)
        .filter(content__product_id__in=product_ids)
        .values("content__product_id")
        .annotate(count=Count("content_id", distinct=True))
    }
    issue_counts = {
        row["analysis__content__product_id"]: row["count"]
        for row in issue_aspects(params)
        .filter(analysis__content__product_id__in=product_ids)
        .values("analysis__content__product_id")
        .annotate(count=Count("analysis__content_id", distinct=True))
    }
    top_issues: dict[int, str] = {}
    for row in issue_rows(params):
        top_issues.setdefault(int(row["product_id"]), str(row["name"]))

    return [
        {
            "product_id": product.id,
            "product_name": product.name,
            "valid_feedback": valid_counts.get(product.id, 0),
            "ai_analyzed": analyzed_counts.get(product.id, 0),
            "explicit_issue_feedback": issue_counts.get(product.id, 0),
            "top_issue": top_issues.get(product.id),
            "latest_data_at": review_stats.get(product.id, {}).get("latest_data_at"),
        }
        for product in product_rows
    ]


def comparison(params: Mapping[str, Any]) -> dict[str, Any]:
    left_id = _integer(params, "left_product_id")
    right_id = _integer(params, "right_product_id")
    product_ids = list(Product.objects.filter(is_active=True).order_by("id").values_list("id", flat=True))
    if left_id is None and product_ids:
        left_id = product_ids[0]
    if right_id is None and len(product_ids) > 1:
        right_id = product_ids[1]
    if left_id is None or right_id is None or left_id == right_id:
        raise ValueError("请选择两个不同的产品")

    sides = []
    category_maps: dict[int, dict[str, dict[str, Any]]] = {}
    for product_id in (left_id, right_id):
        scoped = dict(params)
        scoped["product_id"] = product_id
        product = Product.objects.get(pk=product_id)
        data = overview(scoped)
        denominator = data["ai_analyzed"]
        sides.append(
            {
                "product_id": product.id,
                "product_name": product.name,
                **data,
                "negative_ratio": round(data["explicit_issue_feedback"] / denominator, 4) if denominator else None,
                "ratio_denominator": denominator,
                "sample_sufficient": denominator >= settings.DASHBOARD_COMPARISON_MIN_SAMPLE,
                "top_issues": issue_rows(scoped)[:5],
            }
        )
        category_maps[product_id] = {row["code"]: row for row in categories(scoped)}
    domain_labels, _ = taxonomy_labels()
    codes = sorted(set(category_maps[left_id]) | set(category_maps[right_id]))
    return {
        "left": sides[0],
        "right": sides[1],
        "minimum_sample": settings.DASHBOARD_COMPARISON_MIN_SAMPLE,
        "reliable": all(side["sample_sufficient"] for side in sides),
        "reliability_message": (
            None
            if all(side["sample_sufficient"] for side in sides)
            else "当前分析样本不足, 暂不支持可靠的产品优劣判断。"
        ),
        "categories": [
            {
                "code": code,
                "name": domain_labels.get(code, code),
                "left": category_maps[left_id].get(code, {"feedback_count": 0, "ratio": None}),
                "right": category_maps[right_id].get(code, {"feedback_count": 0, "ratio": None}),
            }
            for code in codes
        ],
    }


def issue_detail(issue_id: str, params: Mapping[str, Any]) -> dict[str, Any]:
    try:
        product_id_text, topic_code = issue_id.split(":", 1)
        product_id = int(product_id_text)
    except (TypeError, ValueError) as exc:
        raise ValueError("问题标识无效") from exc
    scoped = dict(params)
    scoped["product_id"] = product_id
    scoped["topic"] = topic_code
    row = next((item for item in issue_rows(scoped) if item["topic_code"] == topic_code), None)
    if row is None:
        raise LookupError("问题不存在或不在当前筛选范围")
    evidence = list(
        issue_aspects(scoped)
        .filter(topic_code=topic_code)
        .select_related("analysis__content")
        .values(
            "id",
            "analysis__content_id",
            "analysis__content__title",
            "analysis__content__content",
            "analysis__content__source_url",
            "analysis__content__published_at",
            "analysis__content__collected_at",
            "analysis__summary",
            "evidence_text",
            "confidence",
            "severity",
        )
        .order_by("-analysis__content__published_at", "-id")[:20]
    )
    trend_params = dict(scoped)
    return {
        **row,
        "summary": f"{row['product_name']} 用户反馈中的“{row['name']}”明确负面问题。",
        "trend": trends(trend_params),
        "evidence": evidence,
    }


def generate_report(
    *, report_type: str, product: Product | None, source: DataSource | None, period_end: datetime | None = None
) -> AggregateReport:
    end = period_end or timezone.now()
    days = 1 if report_type == ReportType.DAILY else 7
    start = end - timedelta(days=days)
    params: dict[str, Any] = {
        "start_date": timezone.localtime(start).date(),
        "end_date": timezone.localtime(end).date(),
    }
    if product:
        params["product_id"] = product.id
    if source:
        params["source_id"] = source.id
    data = overview(params)
    top_issues = issue_rows(params)[:3]
    snapshot = {
        "overview": data,
        "top_issues": top_issues,
        "watchlist": watchlist(params),
        "coverage": {
            "product": product.name if product else "全部产品",
            "source": source.name if source else "全部来源",
            "period_days": days,
            "analyzed_ratio": round(data["ai_analyzed"] / data["valid_feedback"], 4)
            if data["valid_feedback"]
            else None,
        },
        "data_insufficient": data["ai_analyzed"] < settings.DASHBOARD_COMPARISON_MIN_SAMPLE,
        "disclaimer": data["disclaimer"],
    }
    report_name = "每日摘要" if report_type == ReportType.DAILY else "最近 7 日趋势"
    title = f"{product.name if product else '全部产品'} · {report_name}"
    with transaction.atomic():
        report, _ = AggregateReport.objects.update_or_create(
            product=product,
            source=source,
            report_type=report_type,
            period_start=start,
            period_end=end,
            defaults={
                "title": title,
                "status": ReportStatus.READY,
                "snapshot": json.loads(json.dumps(snapshot, cls=DjangoJSONEncoder)),
                "generated_at": timezone.now(),
                "data_cutoff": data["latest_data_at"],
                "error_message": "",
            },
        )
    return report


def today_token_usage() -> int:
    today = timezone.localdate()
    start = timezone.make_aware(datetime.combine(today, time.min), timezone.get_current_timezone())
    governance = ReviewQuality.objects.none()  # keeps imports and query construction explicit for type checking
    del governance
    from apps.reviews.models import GovernanceAIBatch

    governance_tokens = sum(
        (row["prompt_tokens"] or 0) + (row["completion_tokens"] or 0)
        for row in GovernanceAIBatch.objects.filter(created_at__gte=start).values("prompt_tokens", "completion_tokens")
    )
    structured_tokens = sum(
        (row["input_tokens"] or 0) + (row["output_tokens"] or 0)
        for row in AnalysisRun.objects.filter(created_at__gte=start).values("input_tokens", "output_tokens")
    )
    return governance_tokens + structured_tokens
