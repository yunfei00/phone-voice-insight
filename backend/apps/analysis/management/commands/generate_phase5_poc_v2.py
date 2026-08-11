"""Generate the fixed Phase 5.2 preview sample without invoking an AI provider."""

# ruff: noqa: RUF001

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand, CommandParser

from apps.analysis.services.input_builder import PHASE5_PRODUCT, PHASE5_SOURCE
from apps.analysis.services.sample_preview import render_sample_preview_markdown, select_phase5_poc_v2
from apps.analysis.services.sampling import sample_coverage
from apps.reviews.models import AnalysisCorpusItem
from apps.reviews.services.constants import CORPUS_VERSION


class Command(BaseCommand):
    help = "生成 phase5-poc-v2 固定20条样本及人工预览，不调用AI"

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--output-dir",
            default=str(Path(settings.BASE_DIR) / "docs" / "evaluation"),
            help="输出目录",
        )

    def handle(self, *args: object, **options: Any) -> None:
        del args
        queryset = AnalysisCorpusItem.objects.filter(
            corpus_version=CORPUS_VERSION,
            product__normalized_name=PHASE5_PRODUCT,
            source__code=PHASE5_SOURCE,
        )
        items = select_phase5_poc_v2(queryset)
        output_dir = Path(str(options["output_dir"]))
        output_dir.mkdir(parents=True, exist_ok=True)
        manifest_path = output_dir / "phase5-poc-sample-v2.json"
        preview_path = output_dir / "phase5-poc-v2-preview.md"
        manifest = {
            "sample_version": "phase5-poc-v2",
            "seed": 20260808,
            "review_ids": [item.review_id for item in items],
        }
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        preview_path.write_text(render_sample_preview_markdown(items), encoding="utf-8")
        self.stdout.write(
            json.dumps(
                {
                    "sample_version": "phase5-poc-v2",
                    "ai_called": False,
                    "manifest": str(manifest_path),
                    "preview": str(preview_path),
                    "review_ids": manifest["review_ids"],
                    "coverage": sample_coverage(items),
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )
