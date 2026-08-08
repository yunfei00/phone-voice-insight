import django_filters

from apps.reviews.models import ReviewQuality, ReviewRecord


class ReviewRecordFilter(django_filters.FilterSet):
    source = django_filters.CharFilter(method="filter_source")
    rating = django_filters.NumberFilter(field_name="rating")
    product_variant = django_filters.NumberFilter(field_name="product_variant")
    published_at_after = django_filters.IsoDateTimeFilter(field_name="published_at", lookup_expr="gte")
    published_at_before = django_filters.IsoDateTimeFilter(field_name="published_at", lookup_expr="lte")

    def filter_source(self, queryset, name: str, value: str):  # type: ignore[no-untyped-def]
        del name
        if value.isdigit():
            return queryset.filter(source_id=int(value))
        return queryset.filter(source__code__iexact=value)

    class Meta:
        model = ReviewRecord
        fields = (
            "source",
            "product",
            "product_variant",
            "rating",
            "record_type",
            "author_role",
            "is_official",
        )


class ReviewQualityFilter(django_filters.FilterSet):
    eligible = django_filters.BooleanFilter(field_name="eligible_for_ai")
    exclusion_reason = django_filters.CharFilter(field_name="exclusion_reason")
    record_type = django_filters.CharFilter(field_name="review__record_type")
    author_role = django_filters.CharFilter(field_name="review__author_role")
    product = django_filters.NumberFilter(field_name="review__product_id")
    source = django_filters.CharFilter(method="filter_source")
    quality_score_min = django_filters.NumberFilter(field_name="quality_score", lookup_expr="gte")
    quality_score_max = django_filters.NumberFilter(field_name="quality_score", lookup_expr="lte")

    def filter_source(self, queryset, name: str, value: str):  # type: ignore[no-untyped-def]
        del name
        if value.isdigit():
            return queryset.filter(review__source_id=int(value))
        return queryset.filter(review__source__code__iexact=value)

    class Meta:
        model = ReviewQuality
        fields = (
            "eligible",
            "exclusion_reason",
            "record_type",
            "author_role",
            "product",
            "source",
            "manual_override",
        )
