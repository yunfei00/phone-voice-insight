"""Filters for review analysis results."""

import django_filters
from django.db.models import QuerySet

from apps.analysis.models import AnalysisResult


class AnalysisResultFilter(django_filters.FilterSet):
    aspect = django_filters.CharFilter(method="filter_aspect")
    sentiment = django_filters.CharFilter(method="filter_sentiment")
    confidence_min = django_filters.NumberFilter(field_name="confidence", lookup_expr="gte")
    confidence_max = django_filters.NumberFilter(field_name="confidence", lookup_expr="lte")
    record_type = django_filters.CharFilter(field_name="review__record_type")

    class Meta:
        model = AnalysisResult
        fields = ("status", "provider", "model_name", "prompt_version", "review", "batch")

    def filter_aspect(self, queryset: QuerySet[AnalysisResult], _name: str, value: str) -> QuerySet[AnalysisResult]:
        return queryset.filter(aspects__aspect=value).distinct()

    def filter_sentiment(self, queryset: QuerySet[AnalysisResult], _name: str, value: str) -> QuerySet[AnalysisResult]:
        return queryset.filter(aspects__sentiment=value).distinct()
