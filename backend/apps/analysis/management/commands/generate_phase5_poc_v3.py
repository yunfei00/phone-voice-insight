"""Generate the final fixed Phase 5 v3 sample without invoking AI."""

# ruff: noqa: RUF001

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand, CommandParser

from apps.analysis.services.input_builder import PHASE5_PRODUCT, PHASE5_SOURCE
from apps.analysis.services.phase5_v3_sample import PHASE5_V3_SEED, select_phase5_poc_v3
from apps.analysis.services.sampling import sample_coverage
from apps.reviews.models import AnalysisCorpusItem, ContentPurpose
from apps.reviews.services.constants import CORPUS_VERSION


class Command(BaseCommand):
    help = "生成最终 phase5-poc-v3 固定20条样本，不调用AI"

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--output-dir",
            default=str(Path(settings.BASE_DIR) / "docs" / "evaluation"),
        )

    def handle(self, *_args: object, **options: Any) -> None:
        queryset = AnalysisCorpusItem.objects.filter(
            corpus_version=CORPUS_VERSION,
            product__normalized_name=PHASE5_PRODUCT,
            source__code=PHASE5_SOURCE,
        )
        items, excluded_v2_ids = select_phase5_poc_v3(queryset)
        output_dir = Path(str(options["output_dir"]))
        output_dir.mkdir(parents=True, exist_ok=True)
        manifest_path = output_dir / "phase5-poc-sample-v3.json"
        manifest = {
            "sample_version": "phase5-poc-v3",
            "seed": PHASE5_V3_SEED,
            "review_ids": [item.review_id for item in items],
        }
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        coverage = sample_coverage(items)
        coverage["question"] = sum(item.quality.content_purpose == ContentPurpose.QUESTION for item in items)
        self.stdout.write(
            json.dumps(
                {
                    "sample_version": "phase5-poc-v3",
                    "ai_called": False,
                    "manifest": str(manifest_path),
                    "review_ids": manifest["review_ids"],
                    "excluded_v2_review_ids": excluded_v2_ids,
                    "coverage": coverage,
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )
