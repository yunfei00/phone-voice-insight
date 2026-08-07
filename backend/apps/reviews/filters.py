import django_filters

from apps.reviews.models import ReviewRecord


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
