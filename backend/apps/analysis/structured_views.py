from __future__ import annotations

from collections import Counter
from datetime import timedelta
from typing import Any, cast

from ai.taxonomy import load_taxonomy
from ai.validation import validate_structured_payload
from django.contrib.auth.models import User
from django.core.cache import cache
from django.db import transaction
from django.db.models import Count, Q, QuerySet
from django.db.models.functions import TruncDate
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.viewsets import ReadOnlyModelViewSet, ViewSet

from apps.accounts.ai_service import get_user_ai_provider
from apps.accounts.permissions import IsAnalystOrAdministrator
from apps.analysis.models import (
    AnalysisBatch,
    AnalysisBatchStatus,
    AnalysisReviewRecord,
    AnalysisRun,
    OpinionAspect,
    StructuredAnalysis,
    StructuredRunStatus,
)
from apps.analysis.structured_serializers import (
    AnalysisRunSerializer,
    OpinionAspectSerializer,
    ReviewCorrectionSerializer,
    StructuredAnalysisSerializer,
    StructuredBatchCreateSerializer,
    StructuredBatchSerializer,
)
from apps.analysis.tasks import dispatch_pending_structured_reviews, run_structured_analysis_batch_task
from apps.products.models import Product
from apps.reviews.models import ReviewRecord
from apps.reviews.services.final_corpus import final_corpus_reviews
from apps.sources.models import DataSource


class TaxonomyViewSet(ViewSet):
    def list(self, _request: Request) -> Response:
        taxonomy = load_taxonomy()
        return Response(taxonomy.model_dump())


class StructuredRunViewSet(ReadOnlyModelViewSet):
    serializer_class = AnalysisRunSerializer
    filterset_fields = ("status", "provider", "model", "content", "batch", "is_current")
    ordering_fields = ("created_at", "completed_at", "latency_ms", "estimated_cost")

    def get_queryset(self):  # type: ignore[no-untyped-def]
        return AnalysisRun.objects.select_related("content", "structured_analysis")


class StructuredBatchViewSet(ViewSet):
    permission_classes = (IsAnalystOrAdministrator,)

    def list(self, request: Request) -> Response:
        queryset = AnalysisBatch.objects.filter(prompt_version="structured_analysis_v1", dry_run=False).select_related(
            "product", "source"
        )
        if product_id := request.query_params.get("product"):
            queryset = queryset.filter(product_id=int(product_id))
        if source_id := request.query_params.get("source"):
            queryset = queryset.filter(source_id=int(source_id))
        page = max(int(request.query_params.get("page", 1)), 1)
        page_size = min(max(int(request.query_params.get("page_size", 20)), 1), 100)
        start = (page - 1) * page_size
        count = queryset.count()
        return Response(
            {
                "count": count,
                "next": page + 1 if start + page_size < count else None,
                "previous": page - 1 if page > 1 else None,
                "results": StructuredBatchSerializer(queryset[start : start + page_size], many=True).data,
            }
        )

    def retrieve(self, _request: Request, pk: str | None = None) -> Response:
        assert pk is not None
        batch = AnalysisBatch.objects.select_related("product", "source").get(pk=pk)
        return Response(StructuredBatchSerializer(batch).data)

    def create(self, request: Request) -> Response:
        serializer = StructuredBatchCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        queryset = final_corpus_reviews().select_related("product", "source").order_by("id")
        if ids := values.get("content_ids"):
            queryset = queryset.filter(id__in=ids)
        if product_id := values.get("product_id"):
            queryset = queryset.filter(product_id=product_id)
        if source_id := values.get("source_id"):
            queryset = queryset.filter(source_id=source_id)
        if after := values.get("published_at_after"):
            queryset = queryset.filter(published_at__gte=after)
        if before := values.get("published_at_before"):
            queryset = queryset.filter(published_at__lte=before)
        completed_ids = AnalysisRun.objects.filter(
            status__in=(StructuredRunStatus.SUCCEEDED, StructuredRunStatus.REVIEW_REQUIRED),
            is_current=True,
        ).values("content_id")
        queryset = queryset.exclude(id__in=completed_ids)
        content_ids = list(queryset.values_list("id", flat=True)[: values["max_items"]])
        first = queryset.first()
        if first is None:
            return Response({"error_code": "NO_CONTENT_MATCHED"}, status=status.HTTP_400_BAD_REQUEST)
        product = Product.objects.get(pk=first.product_id)
        source = DataSource.objects.get(pk=first.source_id)
        estimated_characters = sum(
            len(text) for text in queryset.filter(id__in=content_ids).values_list("content", flat=True)
        )
        estimated_tokens = max((estimated_characters + 3) // 4, len(content_ids) * 100)
        estimated_cost = estimated_tokens * values["input_cost_per_million"] / 1_000_000
        if values["dry_run"]:
            return Response(
                {
                    "dry_run": True,
                    "preview": {
                        "matched_count": len(content_ids),
                        "estimated_tokens": estimated_tokens,
                        "estimated_cost": str(estimated_cost),
                        "cost_estimate_reliable": bool(
                            values["input_cost_per_million"] or values["output_cost_per_million"]
                        ),
                    },
                    "matched_content_ids": content_ids,
                    "batch": None,
                    "celery_task_id": None,
                },
                status=status.HTTP_200_OK,
            )
        batch = AnalysisBatch.objects.create(
            created_by=cast(User, request.user),
            product=product,
            source=source,
            corpus_version="structured-v1",
            provider="DRY_RUN" if values["dry_run"] else "USER_CONFIG",
            model_name="NOT_CALLED" if values["dry_run"] else "USER_CONFIG",
            prompt_version="structured_analysis_v1",
            requested_count=len(content_ids),
            dry_run=values["dry_run"],
            max_concurrency=values["max_concurrency"],
            requests_per_minute=values["requests_per_minute"],
            token_limit=values.get("token_limit"),
            cost_budget=values.get("cost_budget"),
            estimated_cost=estimated_cost,
            input_cost_per_million=values["input_cost_per_million"],
            output_cost_per_million=values["output_cost_per_million"],
            total_tokens=estimated_tokens,
            status=AnalysisBatchStatus.SUCCESS if values["dry_run"] else AnalysisBatchStatus.PENDING,
            finished_at=timezone.now() if values["dry_run"] else None,
        )
        celery_task_id = None
        if not values["dry_run"]:
            result = run_structured_analysis_batch_task.delay(batch.id, content_ids, max_retries=values["max_retries"])
            celery_task_id = result.id
        return Response(
            {
                "batch": StructuredBatchSerializer(batch).data,
                "celery_task_id": celery_task_id,
                "dry_run": values["dry_run"],
                "matched_content_ids": content_ids,
            },
            status=status.HTTP_201_CREATED,
        )

    @action(detail=False, methods=("get",), url_path="progress")
    def progress(self, request: Request) -> Response:
        raw_product = request.query_params.get("product_id")
        try:
            product_id = int(raw_product or "")
            if product_id <= 0:
                raise ValueError
        except ValueError:
            return Response({"error_code": "PRODUCT_REQUIRED"}, status=status.HTTP_400_BAD_REQUEST)
        corpus = final_corpus_reviews().filter(product_id=product_id)
        completed = AnalysisRun.objects.filter(
            content_id__in=corpus.values("id"),
            is_current=True,
            status__in=(StructuredRunStatus.SUCCEEDED, StructuredRunStatus.REVIEW_REQUIRED),
        ).values("content_id")
        remaining = corpus.exclude(id__in=completed).count()
        active = (
            AnalysisBatch.objects.filter(
                created_by=cast(User, request.user),
                product_id=product_id,
                prompt_version="structured_analysis_v1",
                status__in=(AnalysisBatchStatus.PENDING, AnalysisBatchStatus.RUNNING),
            )
            .order_by("-id")
            .first()
        )
        latest = (
            AnalysisBatch.objects.filter(
                created_by=cast(User, request.user), product_id=product_id, prompt_version="structured_analysis_v1"
            )
            .order_by("-id")
            .first()
        )
        return Response(
            {
                "total": corpus.count(),
                "completed": corpus.filter(id__in=completed).count(),
                "remaining": remaining,
                "active": active is not None,
                "batch": StructuredBatchSerializer(active or latest).data if (active or latest) else None,
            }
        )

    @action(detail=False, methods=("post",), url_path="retry-remaining")
    def retry_remaining(self, request: Request) -> Response:
        """Explicitly retry every unfinished corpus item, including previous failures."""
        product_id = request.data.get("product_id")
        if not isinstance(product_id, int) or product_id <= 0:
            return Response({"error_code": "PRODUCT_REQUIRED"}, status=status.HTTP_400_BAD_REQUEST)
        user = cast(User, request.user)
        lock_key = f"structured-dispatch:{user.pk}:{product_id}"
        if not cache.add(lock_key, "1", timeout=240):
            return Response({"error_code": "DISPATCH_BUSY"}, status=status.HTTP_409_CONFLICT)
        try:
            if AnalysisBatch.objects.filter(
                created_by=user,
                prompt_version="structured_analysis_v1",
                status__in=(AnalysisBatchStatus.PENDING, AnalysisBatchStatus.RUNNING),
            ).exists():
                return Response({"error_code": "ANALYSIS_ALREADY_RUNNING"}, status=status.HTTP_409_CONFLICT)
            try:
                provider = get_user_ai_provider(user)
            except Exception:
                return Response({"error_code": "AI_NOT_CONFIGURED"}, status=status.HTTP_400_BAD_REQUEST)
            completed = AnalysisRun.objects.filter(
                is_current=True,
                status__in=(StructuredRunStatus.SUCCEEDED, StructuredRunStatus.REVIEW_REQUIRED),
            ).values("content_id")
            corpus = final_corpus_reviews().filter(product_id=product_id).exclude(pk__in=completed)
            source_ids = list(corpus.order_by().values_list("source_id", flat=True).distinct())
            queued = 0
            batch_ids = []
            for source_id in source_ids:
                ids = list(corpus.filter(source_id=source_id).order_by("id").values_list("id", flat=True))
                if not ids:
                    continue
                batch = AnalysisBatch.objects.create(
                    created_by=user,
                    product_id=product_id,
                    source_id=source_id,
                    corpus_version="structured-v1",
                    provider=provider.provider_name,
                    model_name=provider.model,
                    prompt_version="structured_analysis_v1",
                    requested_count=len(ids),
                    dry_run=False,
                    max_concurrency=1,
                    requests_per_minute=10,
                    status=AnalysisBatchStatus.PENDING,
                    total_tokens=0,
                )
                try:
                    run_structured_analysis_batch_task.delay(batch.id, ids)
                except Exception as exc:
                    batch.status = AnalysisBatchStatus.FAILED
                    batch.error_message = f"TASK_DISPATCH_FAILED: {type(exc).__name__}: {exc}"[:1000]
                    batch.finished_at = timezone.now()
                    batch.save(update_fields=("status", "error_message", "finished_at", "updated_at"))
                    continue
                queued += len(ids)
                batch_ids.append(batch.id)
            return Response(
                {"queued": queued, "batch_ids": batch_ids},
                status=status.HTTP_202_ACCEPTED if queued else status.HTTP_200_OK,
            )
        finally:
            cache.delete(lock_key)

    @action(detail=False, methods=("post",), url_path="run-all")
    def run_all(self, request: Request) -> Response:
        product_id = request.data.get("product_id")
        if not isinstance(product_id, int) or product_id <= 0:
            return Response({"error_code": "PRODUCT_REQUIRED"}, status=status.HTTP_400_BAD_REQUEST)
        result = dispatch_pending_structured_reviews(request.user.pk, product_id)
        if result.get("locked"):
            return Response({"error_code": "DISPATCH_BUSY"}, status=status.HTTP_409_CONFLICT)
        if result.get("active_batch_id"):
            return Response(
                {"error_code": "ANALYSIS_ALREADY_RUNNING", "batch_id": result["active_batch_id"]},
                status=status.HTTP_409_CONFLICT,
            )
        if result.get("error_code"):
            return Response(result, status=status.HTTP_400_BAD_REQUEST)
        return Response(result, status=status.HTTP_202_ACCEPTED if result.get("batch_id") else status.HTTP_200_OK)

    @action(detail=True, methods=("post",))
    def cancel(self, _request: Request, pk: str | None = None) -> Response:
        assert pk is not None
        batch = AnalysisBatch.objects.get(pk=pk)
        if batch.status in (AnalysisBatchStatus.PENDING, AnalysisBatchStatus.RUNNING, AnalysisBatchStatus.PAUSED):
            batch.status = AnalysisBatchStatus.CANCELLED
            batch.cancelled_at = timezone.now()
            batch.save()
        return Response(StructuredBatchSerializer(batch).data)

    @action(detail=True, methods=("post",))
    def pause(self, _request: Request, pk: str | None = None) -> Response:
        assert pk is not None
        batch = AnalysisBatch.objects.get(pk=pk)
        if batch.status in (AnalysisBatchStatus.PENDING, AnalysisBatchStatus.RUNNING):
            batch.status = AnalysisBatchStatus.PAUSED
            batch.save()
        return Response(StructuredBatchSerializer(batch).data)

    @action(detail=True, methods=("post",))
    def resume(self, _request: Request, pk: str | None = None) -> Response:
        assert pk is not None
        batch = AnalysisBatch.objects.get(pk=pk)
        if batch.status != AnalysisBatchStatus.PAUSED:
            return Response({"error_code": "BATCH_NOT_PAUSED"}, status=status.HTTP_409_CONFLICT)
        processed = AnalysisRun.objects.filter(batch=batch).values_list("content_id", flat=True)
        remaining_ids = list(
            ReviewRecord.objects.filter(product=batch.product, source=batch.source)
            .exclude(id__in=processed)
            .values_list("id", flat=True)[: max(batch.requested_count - batch.success_count - batch.failed_count, 0)]
        )
        batch.status = AnalysisBatchStatus.PENDING
        batch.save()
        result = run_structured_analysis_batch_task.delay(batch.id, remaining_ids)
        return Response({"batch": StructuredBatchSerializer(batch).data, "celery_task_id": result.id})

    @action(detail=True, methods=("post",), url_path="retry-failed")
    def retry_failed(self, request: Request, pk: str | None = None) -> Response:
        assert pk is not None
        original = AnalysisBatch.objects.get(pk=pk)
        failed_ids = list(
            AnalysisRun.objects.filter(batch=original, status=StructuredRunStatus.FAILED).values_list(
                "content_id", flat=True
            )
        )
        if not failed_ids:
            return Response({"error_code": "NO_FAILED_ITEMS"}, status=status.HTTP_409_CONFLICT)
        retry = AnalysisBatch.objects.create(
            created_by=cast(User, request.user),
            product=original.product,
            source=original.source,
            corpus_version=original.corpus_version,
            provider=original.provider,
            model_name=original.model_name,
            prompt_version=original.prompt_version,
            requested_count=len(failed_ids),
            dry_run=False,
            max_concurrency=original.max_concurrency,
            requests_per_minute=original.requests_per_minute,
            token_limit=original.token_limit,
            cost_budget=original.cost_budget,
            input_cost_per_million=original.input_cost_per_million,
            output_cost_per_million=original.output_cost_per_million,
        )
        result = run_structured_analysis_batch_task.delay(retry.id, failed_ids)
        return Response(
            {"batch": StructuredBatchSerializer(retry).data, "celery_task_id": result.id},
            status=status.HTTP_201_CREATED,
        )


class StructuredAnalysisViewSet(ReadOnlyModelViewSet):
    serializer_class = StructuredAnalysisSerializer
    search_fields = ("summary", "content__title", "content__content", "aspects__evidence_text")
    ordering_fields = ("created_at", "updated_at")

    def get_queryset(self):  # type: ignore[no-untyped-def]
        queryset = StructuredAnalysis.objects.select_related(
            "run", "content", "content__product", "content__source"
        ).prefetch_related("aspects", "review_history__reviewer")
        params = self.request.query_params
        if value := params.get("product"):
            queryset = queryset.filter(content__product_id=int(value))
        if value := params.get("source"):
            queryset = queryset.filter(content__source_id=int(value))
        if value := params.get("aspect_code"):
            queryset = queryset.filter(aspects__aspect_code=value)
        if value := params.get("topic_code"):
            queryset = queryset.filter(aspects__topic_code=value)
        if value := params.get("sentiment"):
            queryset = queryset.filter(aspects__sentiment=value)
        if value := params.get("review_required"):
            queryset = queryset.filter(review_required=value.lower() == "true")
        return queryset.distinct()

    @action(detail=True, methods=("post",), url_path="review")
    def review(self, request: Request, pk: str | None = None) -> Response:
        del pk
        analysis = self.get_object()
        serializer = ReviewCorrectionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = validate_structured_payload(serializer.validated_data["corrected_result"], analysis.content.content)
        if not result.valid or result.payload is None:
            return Response({"errors": result.errors}, status=status.HTTP_400_BAD_REQUEST)
        payload = result.payload
        original = _analysis_payload(analysis)
        with transaction.atomic():
            AnalysisReviewRecord.objects.create(
                analysis=analysis,
                original_result=original,
                corrected_result=payload.model_dump(),
                reviewer=cast(User, request.user),
                review_reason=serializer.validated_data.get("review_reason", ""),
                reviewed_at=timezone.now(),
            )
            for field in ("overall_sentiment", "language", "content_type", "relevance", "summary", "model_mentions"):
                setattr(analysis, field, getattr(payload, field))
            analysis.review_required = False
            analysis.schema_valid = True
            analysis.save()
            analysis.aspects.all().delete()
            OpinionAspect.objects.bulk_create(
                [OpinionAspect(analysis=analysis, **item.model_dump()) for item in payload.aspects]
            )
            analysis.run.status = StructuredRunStatus.SUCCEEDED
            analysis.run.save(update_fields=("status", "updated_at"))
        return Response(StructuredAnalysisSerializer(self.get_object()).data)

    @action(detail=False, methods=("get",), url_path="quality")
    def quality(self, request: Request) -> Response:
        runs = AnalysisRun.objects.filter(is_current=True)
        analyses = StructuredAnalysis.objects.filter(run__is_current=True)
        if product_id := request.query_params.get("product"):
            runs = runs.filter(content__product_id=int(product_id))
            analyses = analyses.filter(content__product_id=int(product_id))
        if source_id := request.query_params.get("source"):
            runs = runs.filter(content__source_id=int(source_id))
            analyses = analyses.filter(content__source_id=int(source_id))
        total = runs.count()
        successful = runs.filter(
            status__in=(StructuredRunStatus.SUCCEEDED, StructuredRunStatus.REVIEW_REQUIRED)
        ).count()
        schema_valid = analyses.filter(schema_valid=True).count()
        error_distribution = list(
            runs.filter(status=StructuredRunStatus.FAILED)
            .values("error_code")
            .annotate(count=Count("id"))
            .order_by("-count")
        )
        model_comparison = list(
            runs.values("provider", "model")
            .annotate(
                total=Count("id"),
                successful=Count(
                    "id",
                    filter=Q(status__in=(StructuredRunStatus.SUCCEEDED, StructuredRunStatus.REVIEW_REQUIRED)),
                ),
            )
            .order_by("provider", "model")
        )
        return Response(
            {
                "total_runs": total,
                "successful_runs": successful,
                "success_rate": successful / total if total else None,
                "schema_valid_rate": schema_valid / successful if successful else None,
                "review_required": analyses.filter(review_required=True).count(),
                "human_evaluation_status": "NOT_EVALUATED",
                "accuracy_metrics": None,
                "error_distribution": error_distribution,
                "model_comparison": model_comparison,
            }
        )

    @action(detail=False, methods=("get",), url_path="aggregates")
    def aggregates(self, request: Request) -> Response:
        del request
        analyses = self.get_queryset().filter(
            run__is_current=True,
            run__status=StructuredRunStatus.SUCCEEDED,
            schema_valid=True,
            review_required=False,
            content_id__in=final_corpus_reviews().values("pk"),
        )
        aspects = OpinionAspect.objects.filter(analysis__in=analyses)
        by_domain = list(aspects.values("aspect_code").annotate(count=Count("id")).order_by("-count"))
        by_topic = list(aspects.values("topic_code").annotate(count=Count("id")).order_by("-count"))
        by_sentiment = list(aspects.values("sentiment").annotate(count=Count("id")).order_by("-count"))
        by_severity = list(aspects.values("severity").annotate(count=Count("id")).order_by("-count"))
        needs = list(
            aspects.filter(intent="SUGGESTION").values("topic_code").annotate(count=Count("id")).order_by("-count")[:20]
        )
        competitors = Counter(
            product
            for products in aspects.exclude(compared_products=[]).values_list("compared_products", flat=True)
            for product in products
        )
        trend = list(
            aspects.annotate(day=TruncDate("analysis__content__published_at"))
            .values("day", "sentiment")
            .annotate(count=Count("id"))
            .order_by("day", "sentiment")
        )
        product_comparison = list(
            aspects.values("analysis__content__product__name", "topic_code")
            .annotate(content_count=Count("analysis__content_id", distinct=True), opinion_count=Count("id"))
            .order_by("analysis__content__product__name", "-opinion_count")
        )
        version_association = list(
            aspects.exclude(analysis__content__software_version="")
            .values("analysis__content__software_version", "topic_code")
            .annotate(count=Count("id"))
            .order_by("-count")[:100]
        )
        totals = aspects.aggregate(
            content_count=Count("analysis__content_id", distinct=True),
            opinion_count=Count("id"),
        )
        return Response(
            {
                "disclaimer": "论坛反馈占比不等于真实设备故障率",
                "content_count": totals["content_count"],
                "opinion_count": totals["opinion_count"],
                "independent_user_count": None,
                "independent_user_count_reason": "原始数据没有稳定个人标识 不能伪造独立用户数",
                "domain_distribution": by_domain,
                "topic_distribution": by_topic,
                "sentiment_distribution": by_sentiment,
                "severity_distribution": by_severity,
                "requirement_ranking": needs,
                "competitor_mentions": [{"product": key, "count": value} for key, value in competitors.most_common()],
                "sentiment_trend": trend,
                "product_issue_comparison": product_comparison,
                "system_version_association": version_association,
                "high_frequency_clusters": by_topic[:20],
                "anomaly_candidates": _anomalies(aspects),
            }
        )


def _analysis_payload(analysis: StructuredAnalysis) -> dict[str, Any]:
    return {
        "schema_version": analysis.run.schema_version,
        "taxonomy_version": analysis.run.taxonomy_version,
        "overall_sentiment": analysis.overall_sentiment,
        "language": analysis.language,
        "content_type": analysis.content_type,
        "relevance": analysis.relevance,
        "summary": analysis.summary,
        "model_mentions": analysis.model_mentions,
        "aspects": [
            {
                key: value
                for key, value in dict(OpinionAspectSerializer(item).data).items()
                if key not in {"id", "analysis"}
            }
            for item in analysis.aspects.all()
        ],
    }


def _anomalies(aspects: QuerySet[OpinionAspect]) -> list[dict[str, Any]]:
    now = timezone.now()
    recent_start = now - timedelta(days=7)
    baseline_start = recent_start - timedelta(days=28)
    candidates: list[dict[str, Any]] = []
    topic_windows = (
        aspects.values("topic_code")
        .annotate(
            recent=Count(
                "id",
                filter=Q(analysis__content__published_at__gte=recent_start),
            ),
            baseline=Count(
                "id",
                filter=Q(
                    analysis__content__published_at__gte=baseline_start,
                    analysis__content__published_at__lt=recent_start,
                ),
            ),
        )
        .order_by("topic_code")
    )
    for row in topic_windows:
        topic = row["topic_code"]
        recent = row["recent"]
        baseline = row["baseline"]
        expected = baseline / 4
        if recent >= 5 and recent >= max(expected * 2, 5):
            candidates.append(
                {
                    "topic_code": topic,
                    "observed_7d": recent,
                    "baseline_28d": baseline,
                    "expected_7d": expected,
                    "reason": "近7天数量至少5且达到历史周均的2倍",
                }
            )
    return candidates
