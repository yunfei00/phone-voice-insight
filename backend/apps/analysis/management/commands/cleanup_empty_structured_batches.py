"""Safely preview/purge empty structured task shells, never analysis results."""
from datetime import datetime

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Exists, OuterRef
from django.utils import timezone

from apps.analysis.models import AnalysisBatch, AnalysisRun, AnalysisResult


class Command(BaseCommand):
    help = "Preview or delete empty structured batches in an explicit ID range."

    def add_arguments(self, parser):
        parser.add_argument("--min-id", type=int, required=True)
        parser.add_argument("--max-id", type=int, required=True)
        parser.add_argument("--apply", action="store_true")

    def handle(self, *args, **options):
        lower, upper = options["min_id"], options["max_id"]
        if lower <= 0 or upper < lower:
            raise CommandError("Specify a valid positive ID range.")
        queryset = (
            AnalysisBatch.objects.filter(
                pk__gte=lower,
                pk__lte=upper,
                prompt_version="structured_analysis_v1",
                success_count=0,
                failed_count=0,
                skipped_count=0,
                retry_count=0,
                dry_run=False,
            )
            .exclude(status__in=("PENDING", "RUNNING", "PAUSED"))
            .annotate(
                has_run=Exists(AnalysisRun.objects.filter(batch_id=OuterRef("pk"))),
                has_result=Exists(AnalysisResult.objects.filter(batch_id=OuterRef("pk"))),
            )
            .filter(has_run=False, has_result=False)
        )
        count = queryset.count()
        self.stdout.write(f"EMPTY_BATCHES={count} RANGE={lower}..{upper}")
        if not options["apply"]:
            self.stdout.write("DRY_RUN: no data changed; inspect range before --apply.")
            return
        with transaction.atomic():
            deleted, details = queryset.delete()
        self.stdout.write(f"DELETED={deleted} DETAILS={details}")
