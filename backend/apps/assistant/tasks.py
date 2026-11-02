from __future__ import annotations

import logging

from celery import shared_task
from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.assistant.models import RagIndexRun, RagIndexRunStatus, RagIndexStatus
from apps.assistant.rag import index_thread, resolve_thread
from apps.reviews.models import RecordType, ReviewRecord

logger = logging.getLogger(__name__)


@shared_task(name="index_rag_record", autoretry_for=(), max_retries=0)
def index_rag_record(review_id: int) -> dict[str, object]:
    if not settings.RAG_INDEXING_ENABLED:
        return {"status": "disabled", "review_id": review_id}
    record = ReviewRecord.objects.select_related("product", "source").filter(pk=review_id).first()
    if record is None:
        return {"status": "deleted", "review_id": review_id}
    thread = resolve_thread(record)
    if thread is None:
        return {"status": "unresolved", "review_id": review_id}
    document = index_thread(thread)
    return {"status": document.status, "review_id": thread.id, "document_id": document.id}


@shared_task(name="run_rag_backfill")
def run_rag_backfill(run_id: int, batch_size: int = 100) -> dict[str, int | str]:
    run = RagIndexRun.objects.get(pk=run_id)
    run.status = RagIndexRunStatus.RUNNING
    run.started_at = run.started_at or timezone.now()
    run.save(update_fields=("status", "started_at", "updated_at"))
    threads = list(
        ReviewRecord.objects.filter(record_type=RecordType.THREAD, id__gt=run.checkpoint_review_id)
        .select_related("product", "source")
        .order_by("id")[: min(max(batch_size, 1), 500)]
    )
    for thread in threads:
        document = index_thread(thread)
        run.processed_count += 1
        run.checkpoint_review_id = thread.id
        if document.status == RagIndexStatus.INDEXED:
            run.indexed_count += 1
        elif document.status == RagIndexStatus.KEYWORD_ONLY:
            run.keyword_only_count += 1
        else:
            run.failed_count += 1
    remaining = ReviewRecord.objects.filter(record_type=RecordType.THREAD, id__gt=run.checkpoint_review_id).exists()
    if remaining:
        run.status = RagIndexRunStatus.PENDING
    else:
        run.status = RagIndexRunStatus.PARTIAL if run.failed_count else RagIndexRunStatus.SUCCESS
        run.finished_at = timezone.now()
    run.save()
    if remaining:
        transaction.on_commit(lambda: run_rag_backfill.delay(run.id, batch_size))
    return {"status": run.status, "processed": run.processed_count, "failed": run.failed_count}


@shared_task(name="reconcile_rag_index")
def reconcile_rag_index() -> dict[str, int | str]:
    if not settings.RAG_INDEXING_ENABLED:
        return {"status": "disabled", "queued": 0}
    ids = list(
        ReviewRecord.objects.filter(record_type=RecordType.THREAD)
        .filter(Q(rag_document__isnull=True) | Q(rag_document__status=RagIndexStatus.FAILED))
        .values_list("id", flat=True)[:100]
    )
    for review_id in ids:
        try:
            index_rag_record.delay(review_id)
        except Exception:  # pragma: no cover - broker failures are reported without blocking collection
            logger.exception("RAG 索引任务投递失败 review_id=%s", review_id)
    return {"status": "ok", "queued": len(ids)}
