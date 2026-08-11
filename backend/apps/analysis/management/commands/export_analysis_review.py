"""Export one analysis batch as a privacy-minimized human review document."""

from django.core.management.base import BaseCommand, CommandError, CommandParser

from apps.analysis.models import AnalysisBatch
from apps.analysis.services.review_report import render_batch_review_markdown


class Command(BaseCommand):
    help = "Render a Phase 5 batch as Markdown without author identifiers"

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--batch-id", type=int, required=True)

    def handle(self, *_args: object, **options: object) -> None:
        batch_id = options["batch_id"]
        if not isinstance(batch_id, int):
            raise CommandError("INVALID_ANALYSIS_BATCH_ID")
        batch = AnalysisBatch.objects.filter(pk=batch_id).first()
        if batch is None:
            raise CommandError("ANALYSIS_BATCH_NOT_FOUND")
        self.stdout.write(render_batch_review_markdown(batch), ending="")
