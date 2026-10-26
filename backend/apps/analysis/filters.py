"""Filters for review analysis results."""

import django_filters
from django.db.models import Count, Q, QuerySet
from rest_framework.exceptions import ValidationError

from apps.analysis.models import AnalysisBatch, AnalysisResult
from apps.analysis.services.evaluation_samples import load_evaluation_sample


class AnalysisResultFilter(django_filters.FilterSet):
    aspect = django_filters.CharFilter(method="filter_aspect")
    sentiment = django_filters.CharFilter(method="filter_sentiment")
    confidence_min = django_filters.NumberFilter(field_name="confidence", lookup_expr="gte")
    confidence_max = django_filters.NumberFilter(field_name="confidence", lookup_expr="lte")
    record_type = django_filters.CharFilter(field_name="review__record_type")
    sample_version = django_filters.CharFilter(method="filter_sample_version")

    class Meta:
        model = AnalysisResult
        fields = ("status", "provider", "model_name", "prompt_version", "review", "batch")

    def filter_aspect(self, queryset: QuerySet[AnalysisResult], _name: str, value: str) -> QuerySet[AnalysisResult]:
        return queryset.filter(aspects__aspect=value).distinct()

    def filter_sentiment(self, queryset: QuerySet[AnalysisResult], _name: str, value: str) -> QuerySet[AnalysisResult]:
        return queryset.filter(aspects__sentiment=value).distinct()

    def filter_sample_version(
        self, queryset: QuerySet[AnalysisResult], _name: str, value: str
    ) -> QuerySet[AnalysisResult]:
        try:
            sample = load_evaluation_sample(value)
        except ValueError as exc:
            raise ValidationError({"sample_version": [str(exc)]}) from exc
        if value == "phase5-poc-v3":
            latest_complete_batch = (
                AnalysisBatch.objects.filter(prompt_version="review_analysis_v3")
                .annotate(
                    sample_result_count=Count(
                        "results",
                        filter=Q(results__review_id__in=sample.review_ids),
                        distinct=True,
                    )
                )
                .filter(sample_result_count=len(sample.review_ids))
                .order_by("-created_at")
                .first()
            )
            if latest_complete_batch is None:
                return queryset.none()
            return queryset.filter(batch=latest_complete_batch, review_id__in=sample.review_ids)
        return queryset.filter(review_id__in=sample.review_ids)
