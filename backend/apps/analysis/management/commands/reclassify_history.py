"""Safely enqueue historical structured reclassification in bounded batches.

Usage:
  python manage.py reclassify_history --user-id 1 --dry-run
  python manage.py reclassify_history --user-id 1 --execute
"""
from __future__ import annotations

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.analysis.models import AnalysisBatch, AnalysisBatchStatus, AnalysisRun, StructuredRunStatus
from apps.analysis.tasks import run_structured_analysis_batch_task
from apps.reviews.services.final_corpus import final_corpus_reviews


class Command(BaseCommand):
    help = "Queue eligible historical reviews for forced reclassification; existing successful results remain published until replacement succeeds."

    def add_arguments(self, parser):
        parser.add_argument("--user-id", type=int, required=True)
        parser.add_argument("--product-id", type=int)
        parser.add_argument("--chunk-size", type=int, default=100)
        parser.add_argument("--execute", action="store_true")
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--restart", action="store_true", help="Explicitly reprocess even completed reclassification records")

    def handle(self, *args, **options):
        if options["execute"] == options["dry_run"]:
            raise CommandError("Specify exactly one of --execute or --dry-run")
        chunk_size = options["chunk_size"]
        if not 1 <= chunk_size <= 500:
            raise CommandError("--chunk-size must be between 1 and 500")
        user = get_user_model().objects.filter(pk=options["user_id"], is_active=True).first()
        if user is None:
            raise CommandError("Active user not found")
        if AnalysisBatch.objects.filter(
            prompt_version="structured_analysis_v1",
            status__in=(AnalysisBatchStatus.PENDING, AnalysisBatchStatus.RUNNING),
        ).exists():
            raise CommandError("Another structured analysis batch is active; wait before starting")
        corpus = final_corpus_reviews().order_by("id")
        if options["product_id"]:
            corpus = corpus.filter(product_id=options["product_id"])
        if not options["restart"]:
            current = AnalysisRun.objects.filter(
                is_current=True, batch__corpus_version="structured-reclass-v2",
                status__in=(StructuredRunStatus.SUCCEEDED, StructuredRunStatus.REVIEW_REQUIRED),
            ).values("content_id")
            corpus = corpus.exclude(pk__in=current)
        count = corpus.count()
        self.stdout.write(f"Eligible records: {count}; chunk size: {chunk_size}; execute: {options['execute']}")
        if not options["execute"]:
            return
        # A single bounded batch per invocation prevents uncontrolled queue flooding.
        ids = list(corpus.values_list("id", flat=True)[:chunk_size])
        if not ids:
            return
        first = corpus.first()
        assert first is not None
        # Keep batches homogeneous by product/source for existing reporting contracts.
        ids = list(corpus.filter(product_id=first.product_id, source_id=first.source_id).values_list("id", flat=True)[:chunk_size])
        with transaction.atomic():
            batch = AnalysisBatch.objects.create(
                created_by=user, product_id=first.product_id, source_id=first.source_id,
                corpus_version="structured-reclass-v2", provider="USER_CONFIG", model_name="USER_CONFIG",
                prompt_version="structured_analysis_v1", requested_count=len(ids),
                dry_run=False, max_concurrency=1, requests_per_minute=10,
                status=AnalysisBatchStatus.PENDING, total_tokens=0,
            )
            transaction.on_commit(
                lambda: run_structured_analysis_batch_task.delay(
                    batch.id, ids, force_reclassify=True, max_retries=1
                )
            )
        self.stdout.write(self.style.SUCCESS(f"Queued batch {batch.id}: {len(ids)} records"))
