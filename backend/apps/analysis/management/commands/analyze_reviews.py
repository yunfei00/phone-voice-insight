"""Run or preview structured analysis from eligible governance corpus only."""

from __future__ import annotations

import json
from typing import Any

from ai.providers import AIProviderError, get_ai_provider
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError, CommandParser

from apps.analysis.models import AnalysisBatch, AnalysisResult, AnalysisStatus, AspectResult
from apps.analysis.services.analysis_runner import error_counts, outcome_dict, run_analysis_batch
from apps.analysis.services.input_builder import PHASE5_PRODUCT, PHASE5_SOURCE, compute_input_hash
from apps.analysis.services.prompt_loader import load_review_prompt
from apps.analysis.services.sampling import DEFAULT_SAMPLE_SEED, sample_coverage, select_corpus_items
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


def _parse_record_ids(value: str) -> list[int]:
    try:
        record_ids = [int(item.strip()) for item in value.split(",") if item.strip()]
    except ValueError as exc:
        raise CommandError("INVALID_RECORD_IDS") from exc
    if not record_ids or any(record_id <= 0 for record_id in record_ids):
        raise CommandError("INVALID_RECORD_IDS")
    if len(record_ids) != len(set(record_ids)):
        raise CommandError("DUPLICATE_RECORD_IDS")
    return record_ids


class Command(BaseCommand):
    help = "从 eligible AnalysisCorpusItem 执行可追溯结构化分析"

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--product", required=True)
        parser.add_argument("--source", required=True)
        parser.add_argument("--limit", type=int)
        parser.add_argument("--record-id", type=int)
        parser.add_argument("--record-ids", default="")
        parser.add_argument("--prompt-version", default="review_analysis_v2")
        parser.add_argument("--retry-failed", action="store_true")
        parser.add_argument("--force", action="store_true")
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--show-selected-ids", action="store_true")
        parser.add_argument("--allow-large-run", action="store_true")
        parser.add_argument("--seed", type=int, default=DEFAULT_SAMPLE_SEED)

    def handle(self, *_args: object, **options: Any) -> None:
        limit = options["limit"]
        record_ids = _parse_record_ids(options["record_ids"]) if options["record_ids"] else []
        if limit is not None and not 1 <= limit <= 10_000:
            raise CommandError("--limit 必须在 1 到 10000 之间")
        if options["record_id"] is not None and limit not in (None, 1):
            raise CommandError("--record-id 不能与大于 1 的 --limit 同时使用")
        if record_ids and (options["record_id"] is not None or limit is not None):
            raise CommandError("--record-ids 不能与 --record-id 或 --limit 同时使用")
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
        if record_ids:
            item_map = {item.review_id: item for item in queryset.filter(review_id__in=record_ids)}
            missing_ids = [record_id for record_id in record_ids if record_id not in item_map]
            if missing_ids:
                raise CommandError(f"ELIGIBLE_CORPUS_ITEMS_NOT_FOUND:{','.join(map(str, missing_ids))}")
            items = [item_map[record_id] for record_id in record_ids]
        else:
            items = select_corpus_items(
                queryset,
                limit=1 if options["record_id"] is not None else limit,
                record_id=options["record_id"],
                seed=options["seed"],
            )
        if options["record_id"] is not None and not items:
            raise CommandError("ELIGIBLE_CORPUS_ITEM_NOT_FOUND")
        if not items:
            raise CommandError("NO_ELIGIBLE_CORPUS_ITEMS")
        if not options["dry_run"] and len(items) > 20 and not options["allow_large_run"]:
            raise CommandError("LARGE_RUN_REQUIRES_ALLOW_LARGE_RUN")
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
                "sample_coverage": sample_coverage(items),
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
            if options["show_selected_ids"]:
                output["selected_review_ids"] = [item.review_id for item in items]
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
        errors = error_counts(outcomes)
        provider_failure = sum(
            count for code, count in errors.items() if code.startswith("AI_") and code != "AI_TIMEOUT"
        )
        output = {
            "dry_run": False,
            "batch_id": batch.id,
            "status": batch.status,
            "requested": len(items),
            "attempted": sum(outcome.attempts > 0 for outcome in outcomes),
            "success": batch.success_count,
            "failed": batch.failed_count,
            "skipped": batch.skipped_count,
            "retry_count": batch.retry_count,
            "schema_failure": errors.get("SCHEMA_VALIDATION_FAILED", 0),
            "evidence_failure": errors.get("EVIDENCE_VALIDATION_FAILED", 0),
            "business_validation_failure": errors.get("ANALYSIS_VALIDATION_FAILED", 0),
            "provider_failure": provider_failure,
            "timeout": errors.get("AI_TIMEOUT", 0),
            "errors": errors,
            "aspect_result_count": AspectResult.objects.filter(analysis__batch=batch).count(),
            "prompt_tokens": batch.prompt_tokens,
            "completion_tokens": batch.completion_tokens,
            "total_tokens": batch.total_tokens,
            "results": [outcome_dict(outcome) for outcome in outcomes],
        }
        if len(items) == 1:
            result = (
                AnalysisResult.objects.filter(batch=batch)
                .select_related("review", "corpus_item")
                .prefetch_related("aspects")
                .first()
            )
            if result is not None:
                output["single_result"] = {
                    "review_id": result.review_id,
                    "record_type": result.review.record_type,
                    "content": result.review.content,
                    "context": result.corpus_item.context_text if result.corpus_item else "",
                    "status": result.status,
                    "schema_validation": "PASS" if result.status == AnalysisStatus.SUCCESS else "FAIL",
                    "evidence_validation": "PASS" if result.status == AnalysisStatus.SUCCESS else "FAIL",
                    "database_persistence": "PASS" if result.status == AnalysisStatus.SUCCESS else "FAIL",
                    "aspects": [
                        {
                            "aspect": aspect.aspect,
                            "sentiment": aspect.sentiment,
                            "issue_category": aspect.issue_category,
                            "issue_summary": aspect.issue_summary,
                            "usage_scenario": aspect.usage_scenario,
                            "evidence_text": aspect.evidence_text,
                            "context_dependent": aspect.context_dependent,
                            "context_evidence_text": aspect.context_evidence_text,
                            "context_evidence_review_id": aspect.context_evidence_review_id,
                            "confidence": str(aspect.confidence),
                        }
                        for aspect in result.aspects.all()
                    ],
                }
        self.stdout.write(json.dumps(output, ensure_ascii=False, sort_keys=True))
