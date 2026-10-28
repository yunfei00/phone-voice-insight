"""按 SourceTarget 隔离预览和清理采集数据。"""

from __future__ import annotations

from typing import Any

from celery import current_app
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.analysis.models import AnalysisBatch, AnalysisBatchStatus, AnalysisResult, AnalysisRun, StructuredAnalysis
from apps.collection.models import (
    CollectionSourceLease,
    CollectionStatus,
    CollectionTargetState,
    CollectionTargetStatus,
    CollectionTask,
)
from apps.reviews.models import AnalysisCorpusItem, ReviewQuality, ReviewQualityRun, ReviewRecord
from apps.sources.models import SourceTarget, SourceTargetCleanupAudit

ACTIVE_COLLECTION = (CollectionStatus.PENDING, CollectionStatus.RUNNING, CollectionStatus.PAUSED)
ACTIVE_ANALYSIS = (AnalysisBatchStatus.PENDING, AnalysisBatchStatus.RUNNING, AnalysisBatchStatus.PAUSED)


class CleanupBlocked(RuntimeError):
    pass


def cleanup_preview(target: SourceTarget) -> dict[str, Any]:
    records = ReviewRecord.objects.filter(source_target=target)
    review_ids = records.values("id")
    tasks = CollectionTask.objects.filter(source_target=target)
    return {
        "source_target_id": target.id,
        "product_id": target.product_id,
        "product_name": target.product.name,
        "source_name": target.source.name,
        "target_name": target.name,
        "target_url": target.target_url,
        "thread_count": records.filter(record_type="THREAD").count(),
        "reply_count": records.filter(record_type__in=("REPLY", "OFFICIAL_REPLY")).count(),
        "other_record_count": records.exclude(record_type__in=("THREAD", "REPLY", "OFFICIAL_REPLY")).count(),
        "review_quality_count": ReviewQuality.objects.filter(review_id__in=review_ids).count(),
        "review_quality_run_count": ReviewQualityRun.objects.filter(review_id__in=review_ids).count(),
        "corpus_item_count": AnalysisCorpusItem.objects.filter(review_id__in=review_ids).count(),
        "analysis_result_count": AnalysisResult.objects.filter(review_id__in=review_ids).count(),
        "analysis_run_count": AnalysisRun.objects.filter(content_id__in=review_ids).count(),
        "structured_analysis_count": StructuredAnalysis.objects.filter(content_id__in=review_ids).count(),
        "collection_task_count": tasks.count(),
        "collection_run_count": tasks.filter(runs__isnull=False).values("runs__id").distinct().count(),
        "active_collection_count": tasks.filter(status__in=ACTIVE_COLLECTION).count(),
        "active_analysis_count": AnalysisBatch.objects.filter(
            product=target.product, source=target.source, status__in=ACTIVE_ANALYSIS
        ).count(),
        "other_affected_objects": [],
    }


def _celery_task_active(task_ids: list[int]) -> bool:
    if not task_ids or settings.CELERY_TASK_ALWAYS_EAGER:
        return False
    try:
        active = current_app.control.inspect(timeout=1).active() or {}
    except Exception:
        return False
    wanted = set(task_ids)
    return any(
        item.get("name") == "run_collection_task" and item.get("args") and int(item["args"][0]) in wanted
        for jobs in active.values()
        for item in jobs
    )


def _write_audit(
    target: SourceTarget, operator: Any, *, result: str, counts: dict[str, int] | None = None, error: str = ""
) -> None:
    SourceTargetCleanupAudit.objects.create(
        operator=operator,
        source_target=target,
        source_target_id_snapshot=target.id,
        product_id_snapshot=target.product_id,
        product_name=target.product.name,
        source_name=target.source.name,
        target_url=target.target_url,
        result=result,
        deleted_counts=counts or {},
        error_message=error,
    )


def execute_cleanup(target_id: int, operator: Any) -> dict[str, Any]:
    try:
        with transaction.atomic():
            target = SourceTarget.objects.select_for_update().select_related("product", "source").get(pk=target_id)
            preview = cleanup_preview(target)
            all_task_ids = list(target.collection_tasks.values_list("id", flat=True))
            active_ids = list(target.collection_tasks.filter(status__in=ACTIVE_COLLECTION).values_list("id", flat=True))
            lease = CollectionSourceLease.objects.select_for_update().filter(source=target.source).first()
            lease_active = bool(
                lease and lease.owner_task_id in all_task_ids and lease.expires_at and lease.expires_at > timezone.now()
            )
            if active_ids or lease_active or _celery_task_active(all_task_ids):
                raise CleanupBlocked("存在运行中、排队中或持有来源租约的采集任务")
            if preview["active_analysis_count"]:
                raise CleanupBlocked("存在使用该产品和来源的 AI 分析任务")

            state, _ = CollectionTargetState.objects.get_or_create(source_target=target)
            state.active_task = None
            state.last_full_task = None
            state.last_incremental_task = None
            state.full_verified = False
            state.full_verified_at = None
            state.status = CollectionTargetStatus.NOT_INITIALIZED
            state.last_success_at = None
            state.last_failure_at = None
            state.last_discovered_thread_count = 0
            state.last_verified_thread_count = 0
            state.last_error = ""
            state.save()
            CollectionSourceLease.objects.filter(owner_task__source_target=target).update(
                owner_task=None, expires_at=None
            )
            target.collection_tasks.all().delete()
            ReviewRecord.objects.filter(source_target=target).delete()
            counts = {key: value for key, value in preview.items() if key.endswith("_count")}
            _write_audit(target, operator, result="SUCCESS", counts=counts)
            return {"detail": "指定采集入口的数据已清理", "deleted_counts": counts, "source_target_id": target.id}
    except Exception as exc:
        failed_target = SourceTarget.objects.select_related("product", "source").filter(pk=target_id).first()
        if failed_target is not None:
            _write_audit(failed_target, operator, result="FAILED", error=str(exc))
        raise
