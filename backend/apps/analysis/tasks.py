"""Celery entry points for bounded structured analysis batches."""

from __future__ import annotations

from typing import Any

from celery import shared_task

from apps.analysis.models import AnalysisBatch
from apps.analysis.services.analysis_runner import error_counts, run_analysis_batch
from apps.reviews.models import AnalysisCorpusItem


@shared_task(name="run_analysis_batch_task", autoretry_for=(), max_retries=0)
def run_analysis_batch_task(
    batch_id: int,
    corpus_item_ids: list[int],
    *,
    force: bool = False,
    retry_failed: bool = False,
) -> dict[str, Any]:
    batch = AnalysisBatch.objects.get(pk=batch_id)
    item_map = {
        item.id: item
        for item in AnalysisCorpusItem.objects.filter(id__in=corpus_item_ids).select_related(
            "review", "quality", "product", "source"
        )
    }
    items = [item_map[item_id] for item_id in corpus_item_ids if item_id in item_map]
    outcomes = run_analysis_batch(batch, corpus_items=items, force=force, retry_failed=retry_failed)
    return {
        "batch_id": batch.id,
        "status": batch.status,
        "success": batch.success_count,
        "failed": batch.failed_count,
        "skipped": batch.skipped_count,
        "errors": error_counts(outcomes),
    }
