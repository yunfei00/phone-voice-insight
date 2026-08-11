"""Export one analysis batch as a privacy-minimized human review document."""

from pathlib import Path

from django.core.management.base import BaseCommand, CommandError, CommandParser

from apps.analysis.models import AnalysisBatch
from apps.analysis.services.review_report import render_batch_review_markdown


class Command(BaseCommand):
    help = "Render a Phase 5 batch as Markdown without author identifiers"

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--batch-id", type=int, required=True)
        parser.add_argument("--output")

    def handle(self, *_args: object, **options: object) -> None:
        batch_id = options["batch_id"]
        if not isinstance(batch_id, int):
            raise CommandError("INVALID_ANALYSIS_BATCH_ID")
        batch = AnalysisBatch.objects.filter(pk=batch_id).first()
        if batch is None:
            raise CommandError("ANALYSIS_BATCH_NOT_FOUND")
        markdown = render_batch_review_markdown(batch)
        output = options.get("output")
        if output:
            output_path = Path(str(output))
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(markdown, encoding="utf-8")
            self.stdout.write(str(output_path))
        else:
            self.stdout.write(markdown, ending="")
