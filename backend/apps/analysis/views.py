from typing import Any

from ai.providers import AIProviderError, get_ai_provider
from django.conf import settings
from django.db import models
from django.db.models import Avg, Count
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.viewsets import ReadOnlyModelViewSet, ViewSet

from apps.analysis.filters import AnalysisResultFilter
from apps.analysis.models import AnalysisBatch, AnalysisEvaluation, AnalysisResult, AnalysisStatus
from apps.analysis.serializers import (
    AnalysisBatchCreateSerializer,
    AnalysisBatchSerializer,
    AnalysisEvaluationSerializer,
    AnalysisResultSerializer,
)
from apps.analysis.services.input_builder import PHASE5_PRODUCT, PHASE5_SOURCE
from apps.analysis.services.prompt_loader import load_review_prompt
from apps.analysis.services.sample_preview import load_sample_preview
from apps.analysis.services.sampling import select_corpus_items
from apps.analysis.tasks import run_analysis_batch_task
from apps.products.models import Product
from apps.reviews.models import AnalysisCorpusItem
from apps.reviews.services.constants import CORPUS_VERSION
from apps.sources.models import DataSource


class AnalysisResultViewSet(ReadOnlyModelViewSet):
    queryset = AnalysisResult.objects.select_related("review", "corpus_item", "batch").prefetch_related(
        "aspects", "evaluation"
    )
    serializer_class = AnalysisResultSerializer
    filterset_class = AnalysisResultFilter
    search_fields = ("summary", "review__content")
    ordering_fields = ("analyzed_at", "created_at", "confidence")

    @action(detail=True, methods=("post",), url_path="evaluate")
    def evaluate(self, request: Request, pk: str | None = None) -> Response:
        del pk
        analysis = self.get_object()
        existing = AnalysisEvaluation.objects.filter(analysis=analysis).first()
        serializer = AnalysisEvaluationSerializer(existing, data=request.data)
        serializer.is_valid(raise_exception=True)
        evaluation = serializer.save(analysis=analysis)
        return Response(AnalysisEvaluationSerializer(evaluation).data)

    @action(detail=False, methods=("get",), url_path="sample-preview")
    def sample_preview(self, request: Request) -> Response:
        sample_version = request.query_params.get("sample_version", "phase5-poc-v2")
        try:
            items = load_sample_preview(sample_version)
        except ValueError as exc:
            return Response({"error_code": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(
            {
                "sample_version": sample_version,
                "count": len(items),
                "ai_status": "NOT_RUN" if sample_version == "phase5-poc-v2" else "HISTORICAL",
                "items": [item.as_dict() for item in items],
            }
        )

    @action(detail=False, methods=("get",), url_path="summary")
    def summary(self, _request: Request) -> Response:
        target_results = AnalysisResult.objects.filter(
            corpus_item__corpus_version=CORPUS_VERSION,
            corpus_item__product__normalized_name=PHASE5_PRODUCT,
            corpus_item__source__code=PHASE5_SOURCE,
        )
        eligible = AnalysisCorpusItem.objects.filter(
            corpus_version=CORPUS_VERSION,
            eligible=True,
            quality__eligible_for_ai=True,
            product__normalized_name=PHASE5_PRODUCT,
            source__code=PHASE5_SOURCE,
        ).count()
        successful_review_ids = set(
            target_results.filter(status=AnalysisStatus.SUCCESS).values_list("review_id", flat=True)
        )
        aggregate = target_results.aggregate(
            total=Count("id"),
            success=Count("id", filter=models.Q(status=AnalysisStatus.SUCCESS)),
            failed=Count("id", filter=models.Q(status=AnalysisStatus.FAILED)),
            average_confidence=Avg("confidence", filter=models.Q(status=AnalysisStatus.SUCCESS)),
        )
        evaluations = AnalysisEvaluation.objects.filter(analysis__in=target_results)
        return Response(
            {
                "eligible_corpus": eligible,
                "analyzed_reviews": len(successful_review_ids),
                "success": aggregate["success"],
                "failed": aggregate["failed"],
                "pending": max(eligible - len(successful_review_ids), 0),
                "average_confidence": aggregate["average_confidence"],
                "schema_failures": target_results.filter(error_code="SCHEMA_VALIDATION_FAILED").count(),
                "evidence_failures": target_results.filter(error_code="EVIDENCE_VALIDATION_FAILED").count(),
                "evaluated": evaluations.count(),
                "evaluation_accuracy": _evaluation_accuracy(evaluations),
            }
        )


class AnalysisBatchViewSet(ViewSet):
    def list(self, _request: Request) -> Response:
        queryset = AnalysisBatch.objects.select_related("product", "source")[:100]
        return Response(AnalysisBatchSerializer(queryset, many=True).data)

    def retrieve(self, _request: Request, pk: str | None = None) -> Response:
        batch = get_object_or_404(AnalysisBatch.objects.select_related("product", "source"), pk=pk)
        return Response(AnalysisBatchSerializer(batch).data)

    def create(self, request: Request) -> Response:
        serializer = AnalysisBatchCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        product = get_object_or_404(Product, pk=values["product_id"])
        source = get_object_or_404(DataSource, pk=values["source_id"])
        if product.normalized_name != PHASE5_PRODUCT or source.code != PHASE5_SOURCE:
            return Response({"error_code": "PHASE5_TARGET_ONLY"}, status=status.HTTP_400_BAD_REQUEST)
        if int(values["limit"]) > 20 and not values["allow_large_run"]:
            return Response(
                {"error_code": "LARGE_RUN_REQUIRES_EXPLICIT_CONFIRMATION"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            load_review_prompt(values["prompt_version"])
            provider = get_ai_provider()
        except (ValueError, AIProviderError) as exc:
            code = exc.code if isinstance(exc, AIProviderError) else str(exc)
            return Response({"error_code": code}, status=status.HTTP_400_BAD_REQUEST)
        queryset = AnalysisCorpusItem.objects.filter(
            product=product,
            source=source,
            corpus_version=CORPUS_VERSION,
            eligible=True,
            quality__eligible_for_ai=True,
        )
        items = select_corpus_items(queryset, limit=int(values["limit"]))
        batch = AnalysisBatch.objects.create(
            product=product,
            source=source,
            corpus_version=CORPUS_VERSION,
            provider=provider.provider_name,
            model_name=provider.model,
            prompt_version=values["prompt_version"],
            requested_count=len(items),
        )
        celery_result = run_analysis_batch_task.delay(
            batch.id,
            [item.id for item in items],
            force=values["force"],
            retry_failed=values["retry_failed"],
        )
        return Response(
            {"batch": AnalysisBatchSerializer(batch).data, "celery_task_id": celery_result.id},
            status=status.HTTP_201_CREATED,
        )

    @action(detail=False, methods=("get",), url_path="configuration")
    def configuration(self, _request: Request) -> Response:
        configured = bool(settings.AI_BASE_URL and settings.AI_API_KEY and settings.AI_MODEL)
        return Response(
            {
                "provider": settings.AI_PROVIDER,
                "model": settings.AI_MODEL or "NOT_CONFIGURED",
                "prompt_version": "review_analysis_v3",
                "configured": configured,
                "concurrency": settings.AI_CONCURRENCY,
            }
        )


def _evaluation_accuracy(queryset: Any) -> dict[str, float | None]:
    total = queryset.count()
    if not total:
        return {name: None for name in ("aspect", "sentiment", "issue", "scenario", "evidence")}
    return {
        "aspect": queryset.filter(aspect_correct=True).count() / total,
        "sentiment": queryset.filter(sentiment_correct=True).count() / total,
        "issue": queryset.filter(issue_correct=True).count() / total,
        "scenario": queryset.filter(scenario_correct=True).count() / total,
        "evidence": queryset.filter(evidence_correct=True).count() / total,
    }
