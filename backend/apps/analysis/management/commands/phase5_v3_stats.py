"""Report QA-only distributions for one completed Phase 5 v3 batch."""

# ruff: noqa: RUF001

from __future__ import annotations

import json
from collections import Counter

from django.core.management.base import BaseCommand, CommandError, CommandParser

from apps.analysis.models import AnalysisBatch, AnalysisEvaluation, AnalysisResult, Aspect, AspectResult, Sentiment
from apps.analysis.services.evaluation_samples import load_evaluation_sample
from apps.reviews.models import ContentPurpose


class Command(BaseCommand):
    help = "输出 Phase 5 v3 批次的 QA 分布，不生成产品结论"

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--batch-id", type=int, required=True)

    def handle(self, *_args: object, **options: object) -> None:
        batch_id = options["batch_id"]
        if not isinstance(batch_id, int):
            raise CommandError("INVALID_ANALYSIS_BATCH_ID")
        batch = AnalysisBatch.objects.filter(pk=batch_id).first()
        if batch is None:
            raise CommandError("ANALYSIS_BATCH_NOT_FOUND")
        sample = load_evaluation_sample("phase5-poc-v3")
        results = AnalysisResult.objects.filter(batch=batch, review_id__in=sample.review_ids)
        result_review_ids = set(results.values_list("review_id", flat=True))
        if result_review_ids != set(sample.review_ids):
            raise CommandError("BATCH_DOES_NOT_MATCH_PHASE5_POC_V3")
        aspects = AspectResult.objects.filter(analysis__in=results)
        aspect_counts = Counter(aspects.values_list("aspect", flat=True))
        sentiment_counts = Counter(aspects.values_list("sentiment", flat=True))
        payload = {
            "batch_id": batch.id,
            "analysis_result_count": results.count(),
            "aspect_result_count": aspects.count(),
            "aspect_distribution": {choice: aspect_counts[choice] for choice in Aspect.values},
            "sentiment_distribution": {choice: sentiment_counts[choice] for choice in Sentiment.values},
            "question_count": results.filter(content_purpose=ContentPurpose.QUESTION).count(),
            "not_evaluated": results.filter(evaluation__isnull=True).count(),
            "evaluated": AnalysisEvaluation.objects.filter(analysis__in=results).count(),
            "failed_review_ids": list(
                results.exclude(error_code="").order_by("review_id").values_list("review_id", flat=True)
            ),
            "evidence_failed_review_ids": list(
                results.filter(error_code="EVIDENCE_VALIDATION_FAILED")
                .order_by("review_id")
                .values_list("review_id", flat=True)
            ),
        }
        self.stdout.write(json.dumps(payload, ensure_ascii=False, sort_keys=True))
