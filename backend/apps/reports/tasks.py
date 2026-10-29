"""驾驶舱报告与 Beat 心跳任务。"""

from __future__ import annotations

from datetime import datetime, time
from typing import Any

from celery import shared_task
from django.utils import timezone
from redis.exceptions import RedisError

from apps.common.views import get_redis_client
from apps.products.models import Product
from apps.reports.models import ReportType
from apps.reports.services import generate_report


@shared_task(name="record_dashboard_beat_heartbeat")
def record_dashboard_beat_heartbeat() -> dict[str, Any]:
    timestamp = timezone.now().timestamp()
    try:
        get_redis_client().setex("pvi:celery-beat-heartbeat", 300, str(timestamp))
    except (RedisError, OSError):
        return {"status": "redis_unavailable"}
    return {"status": "ok", "timestamp": timestamp}


@shared_task(name="generate_insight_reports")
def generate_insight_reports(report_type: str) -> dict[str, Any]:
    if report_type not in ReportType.values:
        return {"status": "invalid_report_type", "report_type": report_type}
    current_timezone = timezone.get_current_timezone()
    cutoff = timezone.make_aware(datetime.combine(timezone.localdate(), time.min), current_timezone)
    reports = [generate_report(report_type=report_type, product=None, source=None, period_end=cutoff)]
    for product in Product.objects.filter(is_active=True).order_by("id"):
        reports.append(generate_report(report_type=report_type, product=product, source=None, period_end=cutoff))
    return {"status": "ok", "report_type": report_type, "report_ids": [report.id for report in reports]}
