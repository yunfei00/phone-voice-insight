from __future__ import annotations

import logging

from django.conf import settings
from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.reviews.models import ReviewRecord

logger = logging.getLogger(__name__)


@receiver(post_save, sender=ReviewRecord, dispatch_uid="assistant_queue_rag_index")
def queue_rag_index(sender: type[ReviewRecord], instance: ReviewRecord, **kwargs: object) -> None:
    del sender, kwargs
    if not settings.RAG_INDEXING_ENABLED:
        return

    def dispatch() -> None:
        try:
            from apps.assistant.tasks import index_rag_record

            index_rag_record.delay(instance.id)
        except Exception:  # pragma: no cover - ingestion must survive broker outages
            logger.exception("RAG 索引任务投递失败 review_id=%s", instance.id)

    transaction.on_commit(dispatch)
