"""Filters for review analysis results."""

import django_filters
from django.db.models import QuerySet
from rest_framework.exceptions import ValidationError

from apps.analysis.models import AnalysisResult
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
        return queryset.filter(review_id__in=sample.review_ids)
