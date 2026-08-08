"""Run or preview structured analysis from eligible governance corpus only."""

from __future__ import annotations

import json
from typing import Any

from ai.providers import AIProviderError, get_ai_provider
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError, CommandParser

from apps.analysis.models import AnalysisBatch, AnalysisResult, AnalysisStatus
from apps.analysis.services.analysis_runner import error_counts, outcome_dict, run_analysis_batch
from apps.analysis.services.input_builder import PHASE5_PRODUCT, PHASE5_SOURCE, compute_input_hash
from apps.analysis.services.prompt_loader import load_review_prompt
from apps.analysis.services.sampling import DEFAULT_SAMPLE_SEED, select_corpus_items
from apps.products.models import Product
from apps.reviews.models import AnalysisCorpusItem
from apps.reviews.services.constants import CORPUS_VERSION
from apps.sources.models import DataSource


def _distribution(values: list[int]) -> dict[str, int]:
    if not values:
        return {"min": 0, "p50": 0, "p95": 0, "max": 0}
    ordered = sorted(values)
    return {
        "min": ordered[0],
        "p50": ordered[(len(ordered) - 1) * 50 // 100],
        "p95": ordered[(len(ordered) - 1) * 95 // 100],
        "max": ordered[-1],
    }


class Command(BaseCommand):
    help = "从 eligible AnalysisCorpusItem 执行可追溯结构化分析"

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--product", required=True)
        parser.add_argument("--source", required=True)
        parser.add_argument("--limit", type=int)
        parser.add_argument("--record-id", type=int)
        parser.add_argument("--prompt-version", default="review_analysis_v2")
        parser.add_argument("--retry-failed", action="store_true")
        parser.add_argument("--force", action="store_true")
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--seed", type=int, default=DEFAULT_SAMPLE_SEED)

    def handle(self, *_args: object, **options: Any) -> None:
        limit = options["limit"]
        if limit is not None and not 1 <= limit <= 10_000:
            raise CommandError("--limit 必须在 1 到 10000 之间")
        if options["record_id"] is not None and limit not in (None, 1):
            raise CommandError("--record-id 不能与大于 1 的 --limit 同时使用")
        try:
            load_review_prompt(options["prompt_version"])
        except ValueError as exc:
            raise CommandError(str(exc)) from exc
        product_value = str(options["product"])
        source_value = str(options["source"])
        if product_value.upper() != PHASE5_PRODUCT or source_value.upper() != PHASE5_SOURCE:
            raise CommandError("PHASE5_TARGET_ONLY")
        product = Product.objects.filter(normalized_name__iexact=product_value).first()
        if product is None and product_value.isdigit():
            product = Product.objects.filter(pk=int(product_value)).first()
        source = DataSource.objects.filter(code__iexact=source_value).first()
        if source is None and source_value.isdigit():
            source = DataSource.objects.filter(pk=int(source_value)).first()
        if product is None or source is None:
            raise CommandError("PRODUCT_OR_SOURCE_NOT_FOUND")
        queryset = AnalysisCorpusItem.objects.filter(
            product=product,
            source=source,
            corpus_version=CORPUS_VERSION,
            eligible=True,
            quality__eligible_for_ai=True,
        )
        total_eligible = queryset.count()
        items = select_corpus_items(
            queryset,
            limit=1 if options["record_id"] is not None else limit,
            record_id=options["record_id"],
            seed=options["seed"],
        )
        if options["record_id"] is not None and not items:
            raise CommandError("ELIGIBLE_CORPUS_ITEM_NOT_FOUND")
        if options["dry_run"]:
            provider_name = str(settings.AI_PROVIDER)
            model = str(settings.AI_MODEL)
            hashes = {
                item.review_id: compute_input_hash(item, prompt_version=options["prompt_version"]) for item in items
            }
            analyzed = AnalysisResult.objects.filter(
                review_id__in=hashes,
                model_name=model,
                prompt_version=options["prompt_version"],
                status=AnalysisStatus.SUCCESS,
            )
            analyzed_ids = {result.review_id for result in analyzed if result.input_hash == hashes[result.review_id]}
            output = {
                "dry_run": True,
                "provider": provider_name,
                "model": model or "NOT_CONFIGURED",
                "prompt_version": options["prompt_version"],
                "eligible_corpus": total_eligible,
                "selected": len(items),
                "already_analyzed": len(analyzed_ids),
                "pending": len(items) - len(analyzed_ids),
                "skipped": len(analyzed_ids),
                "estimated_calls": len(items) - len(analyzed_ids),
                "input_lengths": _distribution([len(item.normalized_text) for item in items]),
                "context_lengths": _distribution([len(item.context_text) for item in items]),
                "samples": [
                    {
                        "review_id": item.review_id,
                        "record_type": item.record_type,
                        "normalized_text": item.normalized_text[:100],
                        "context": item.context_text[:150],
                    }
                    for item in items[:5]
                ],
            }
            self.stdout.write(json.dumps(output, ensure_ascii=False, sort_keys=True))
            return
        try:
            provider_instance = get_ai_provider()
        except AIProviderError as exc:
            raise CommandError(exc.code) from exc
        batch = AnalysisBatch.objects.create(
            product=product,
            source=source,
            corpus_version=CORPUS_VERSION,
            provider=provider_instance.provider_name,
            model_name=provider_instance.model,
            prompt_version=options["prompt_version"],
            requested_count=len(items),
        )
        outcomes = run_analysis_batch(
            batch,
            corpus_items=items,
            force=options["force"],
            retry_failed=options["retry_failed"],
        )
        output = {
            "dry_run": False,
            "batch_id": batch.id,
            "status": batch.status,
            "requested": len(items),
            "success": batch.success_count,
            "failed": batch.failed_count,
            "skipped": batch.skipped_count,
            "retry_count": batch.retry_count,
            "errors": error_counts(outcomes),
            "prompt_tokens": batch.prompt_tokens,
            "completion_tokens": batch.completion_tokens,
            "total_tokens": batch.total_tokens,
            "results": [outcome_dict(outcome) for outcome in outcomes],
        }
        self.stdout.write(json.dumps(output, ensure_ascii=False, sort_keys=True))
