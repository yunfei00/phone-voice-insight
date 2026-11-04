"""Start or inspect the resumable historical structured-analysis campaign."""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from apps.analysis.models import AnalysisBatch, AnalysisBatchStatus, AnalysisRun
from apps.analysis.tasks import continue_historical_reclassification
from apps.reviews.services.final_corpus import final_corpus_reviews


class Command(BaseCommand):
    help = "Start historical reclassification; automatically continues one bounded batch at a time."

    def add_arguments(self, parser):
        parser.add_argument("--user-id", type=int, required=True)
        parser.add_argument("--chunk-size", type=int, default=100)
        parser.add_argument("--execute", action="store_true")
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *_args, **options):
        if options["execute"] == options["dry_run"]:
            raise CommandError("Specify exactly one of --execute or --dry-run")
        chunk_size = options["chunk_size"]
        if not 1 <= chunk_size <= 500:
            raise CommandError("--chunk-size must be between 1 and 500")
        if not get_user_model().objects.filter(pk=options["user_id"], is_active=True).exists():
            raise CommandError("Active user not found")
        attempted = AnalysisRun.objects.filter(batch__corpus_version="structured-reclass-v2").values("content_id")
        pending = final_corpus_reviews().exclude(pk__in=attempted).count()
        active = AnalysisBatch.objects.filter(
            prompt_version="structured_analysis_v1",
            status__in=(AnalysisBatchStatus.PENDING, AnalysisBatchStatus.RUNNING),
        ).exists()
        self.stdout.write(f"Remaining: {pending}; active: {active}; chunk size: {chunk_size}")
        if options["dry_run"]:
            return
        if active:
            raise CommandError("A structured batch is active; retry after it finishes")
        task = continue_historical_reclassification.delay(options["user_id"], chunk_size)
        self.stdout.write(self.style.SUCCESS(f"Enqueued campaign continuation: {task.id}"))
