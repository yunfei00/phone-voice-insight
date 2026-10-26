"""Export one fixed evaluation sample across retry batches."""

from pathlib import Path

from django.core.management.base import BaseCommand, CommandError, CommandParser

from apps.analysis.services.review_report import render_sample_review_markdown


class Command(BaseCommand):
    help = "Render a fixed Phase 5 sample across retry batches"

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--sample-version", required=True)
        parser.add_argument("--prompt-version", default="review_analysis_v3")
        parser.add_argument("--output", required=True)

    def handle(self, *_args: object, **options: object) -> None:
        try:
            markdown = render_sample_review_markdown(
                str(options["sample_version"]),
                prompt_version=str(options["prompt_version"]),
            )
        except ValueError as exc:
            raise CommandError(str(exc)) from exc
        output_path = Path(str(options["output"]))
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(markdown, encoding="utf-8")
        self.stdout.write(str(output_path))
