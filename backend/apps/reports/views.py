"""手机用户声音驾驶舱只读 API。"""

from __future__ import annotations

from typing import Any

from celery import current_app
from django.conf import settings
from django.db import connections
from django.db.utils import DatabaseError
from django.shortcuts import get_object_or_404
from django.utils import timezone
from redis.exceptions import RedisError
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import UserRole
from apps.accounts.permissions import get_user_role
from apps.analysis.models import AnalysisBatch, AnalysisRun, StructuredRunStatus
from apps.collection.models import CollectionSourceLease, CollectionStatus, CollectionTask
from apps.common.views import get_redis_client
from apps.reports.models import AggregateReport
from apps.reports.services import (
    categories,
    comparison,
    issue_detail,
    issue_rows,
    overview,
    product_summaries,
    today_token_usage,
    trends,
    watchlist,
)
from apps.reviews.models import GovernanceAIBatch, GovernanceAIReview, GovernanceTask, ReviewQuality


def _params(request: Request) -> dict[str, Any]:
    return request.query_params.dict()


def _safe_response(callback: Any) -> Response:
    try:
        return Response(callback())
    except ValueError as exc:
        return Response({"error_code": "INVALID_FILTER", "message": str(exc)}, status=status.HTTP_400_BAD_REQUEST)


class DashboardOverviewView(APIView):
    def get(self, request: Request) -> Response:
        return _safe_response(lambda: {**overview(_params(request)), "watchlist": watchlist(_params(request))})


class DashboardTrendsView(APIView):
    def get(self, request: Request) -> Response:
        return _safe_response(lambda: {"results": trends(_params(request))})


class DashboardCategoriesView(APIView):
    def get(self, request: Request) -> Response:
        return _safe_response(lambda: {"results": categories(_params(request))})


class DashboardProductsView(APIView):
    def get(self, request: Request) -> Response:
        return _safe_response(lambda: {"results": product_summaries(_params(request))})


class DashboardComparisonView(APIView):
    def get(self, request: Request) -> Response:
        return _safe_response(lambda: comparison(_params(request)))


class DashboardIssueListView(APIView):
    def get(self, request: Request) -> Response:
        def result() -> dict[str, Any]:
            rows = issue_rows(_params(request))
            page = max(int(request.query_params.get("page", 1)), 1)
            page_size = min(max(int(request.query_params.get("page_size", 10)), 1), 100)
            start = (page - 1) * page_size
            return {
                "count": len(rows),
                "next": page + 1 if start + page_size < len(rows) else None,
                "previous": page - 1 if page > 1 else None,
                "results": rows[start : start + page_size],
            }

        return _safe_response(result)


class DashboardIssueDetailView(APIView):
    def get(self, request: Request, issue_id: str) -> Response:
        try:
            return Response(issue_detail(issue_id, _params(request)))
        except ValueError as exc:
            return Response({"error_code": "INVALID_FILTER", "message": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except LookupError as exc:
            return Response({"error_code": "ISSUE_NOT_FOUND", "message": str(exc)}, status=status.HTTP_404_NOT_FOUND)


def _report_payload(report: AggregateReport, *, include_snapshot: bool) -> dict[str, Any]:
    payload = {
        "id": report.id,
        "report_type": report.report_type,
        "title": report.title,
        "product_id": report.product_id,
        "product_name": report.product.name if report.product else "全部产品",
        "source_id": report.source_id,
        "source_name": report.source.name if report.source else "全部来源",
        "period_start": report.period_start,
        "period_end": report.period_end,
        "generated_at": report.generated_at,
        "data_cutoff": report.data_cutoff,
        "status": report.status,
        "error_message": report.error_message,
    }
    if include_snapshot:
        payload["snapshot"] = report.snapshot
    return payload


class DashboardReportListView(APIView):
    def get(self, request: Request) -> Response:
        queryset = AggregateReport.objects.select_related("product", "source")
        if report_type := request.query_params.get("report_type"):
            queryset = queryset.filter(report_type=report_type)
        if product_id := request.query_params.get("product_id"):
            queryset = queryset.filter(product_id=int(product_id))
        page = max(int(request.query_params.get("page", 1)), 1)
        page_size = min(max(int(request.query_params.get("page_size", 10)), 1), 100)
        start = (page - 1) * page_size
        count = queryset.count()
        return Response(
            {
                "count": count,
                "next": page + 1 if start + page_size < count else None,
                "previous": page - 1 if page > 1 else None,
                "results": [
                    _report_payload(item, include_snapshot=False) for item in queryset[start : start + page_size]
                ],
            }
        )


class DashboardReportDetailView(APIView):
    def get(self, _request: Request, report_id: int) -> Response:
        report = get_object_or_404(AggregateReport.objects.select_related("product", "source"), pk=report_id)
        return Response(_report_payload(report, include_snapshot=True))


class DashboardOperationsView(APIView):
    def get(self, request: Request) -> Response:
        role = get_user_role(request.user)
        database_status = "online"
        try:
            with connections["default"].cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()
        except DatabaseError:
            database_status = "offline"

        redis_status = "online"
        beat_status = "unknown"
        try:
            redis_client = get_redis_client()
            if not redis_client.ping():
                redis_status = "offline"
            heartbeat: Any = redis_client.get("pvi:celery-beat-heartbeat")
            if heartbeat:
                heartbeat_at = float(heartbeat)
                beat_status = "online" if timezone.now().timestamp() - heartbeat_at < 180 else "stale"
        except (RedisError, OSError, ValueError):
            redis_status = "offline"

        worker_status = "unknown"
        try:
            # Celery inspect waits for a broadcast reply and can otherwise dominate the
            # monitoring endpoint latency.  A short timeout is sufficient for the local
            # worker health signal; "offline" remains distinct from business data health.
            replies = current_app.control.inspect(timeout=0.2).ping() or {}
            worker_status = "online" if replies else "offline"
        except Exception:  # Celery inspection must never break monitoring API.
            worker_status = "offline"

        active_collections = CollectionTask.objects.filter(
            status__in=(CollectionStatus.PENDING, CollectionStatus.RUNNING, CollectionStatus.PAUSED)
        ).count()
        last_collection = (
            CollectionTask.objects.filter(status=CollectionStatus.SUCCESS).order_by("-finished_at").first()
        )
        last_analysis = (
            AnalysisRun.objects.filter(status__in=(StructuredRunStatus.SUCCEEDED, StructuredRunStatus.REVIEW_REQUIRED))
            .order_by("-completed_at")
            .first()
        )
        token_usage = today_token_usage()
        budget = settings.AI_AUTOMATION_DAILY_TOKEN_BUDGET
        summary: dict[str, Any] = {
            "role_scope": "full" if role == UserRole.ADMIN else "summary",
            "business_status": {
                "collection": "running" if active_collections else "idle",
                "data_update": "normal" if last_collection else "no_success_record",
                "ai_automation": "enabled" if settings.AI_AUTOMATION_ENABLED else "disabled",
                "ai_message": "自动分析已启用" if settings.AI_AUTOMATION_ENABLED else "自动分析未启用",
            },
            "system": {
                "backend": "online",
                "database": database_status,
                "redis": redis_status,
                "celery_worker": worker_status,
                "celery_beat": beat_status,
            },
            "latest": {
                "collection_at": last_collection.finished_at if last_collection else None,
                "analysis_at": last_analysis.completed_at if last_analysis else None,
            },
            "ai": {
                "today_tokens": token_usage,
                "daily_budget": budget,
                "budget_ratio": round(token_usage / budget, 4) if budget else None,
                "budget_exhausted": bool(budget and token_usage >= budget),
            },
        }
        if role != UserRole.ADMIN:
            return Response(summary)

        summary.update(
            {
                "collection": {
                    "running": CollectionTask.objects.filter(status=CollectionStatus.RUNNING).count(),
                    "waiting": CollectionTask.objects.filter(status=CollectionStatus.PENDING).count(),
                    "recent_success": CollectionTask.objects.filter(status=CollectionStatus.SUCCESS).count(),
                    "recent_failed": CollectionTask.objects.filter(status=CollectionStatus.FAILED).count(),
                    "active_leases": CollectionSourceLease.objects.filter(expires_at__gt=timezone.now()).count(),
                },
                "governance": {
                    "pending": GovernanceTask.objects.filter(status=GovernanceTask.Status.PENDING).count(),
                    "running": GovernanceTask.objects.filter(status=GovernanceTask.Status.RUNNING).count(),
                    "eligible": ReviewQuality.objects.filter(eligible_for_ai=True).count(),
                    "rejected": GovernanceAIReview.objects.filter(status=GovernanceAIReview.Status.REJECTED).count(),
                    "uncertain": GovernanceAIReview.objects.filter(status=GovernanceAIReview.Status.UNCERTAIN).count(),
                    "errors": GovernanceAIReview.objects.filter(status=GovernanceAIReview.Status.ERROR).count(),
                },
                "analysis": {
                    "running_batches": AnalysisBatch.objects.filter(status="RUNNING").count(),
                    "ai_governance_running": GovernanceAIBatch.objects.filter(
                        status=GovernanceAIBatch.Status.RUNNING
                    ).count(),
                    "successful": AnalysisRun.objects.filter(
                        status__in=(StructuredRunStatus.SUCCEEDED, StructuredRunStatus.REVIEW_REQUIRED)
                    ).count(),
                    "failed": AnalysisRun.objects.filter(status=StructuredRunStatus.FAILED).count(),
                },
            }
        )
        from apps.assistant.models import AssistantMessage, MessageRole, MessageStatus

        assistant_messages = AssistantMessage.objects.filter(role=MessageRole.ASSISTANT)
        summary["assistant"] = {
            "running": assistant_messages.filter(status=MessageStatus.RUNNING).count(),
            "completed": assistant_messages.filter(status=MessageStatus.COMPLETED).count(),
            "failed": assistant_messages.filter(status=MessageStatus.FAILED).count(),
            "cancelled": assistant_messages.filter(status=MessageStatus.CANCELLED).count(),
        }
        return Response(summary)
