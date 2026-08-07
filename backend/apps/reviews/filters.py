import django_filters

from apps.reviews.models import ReviewRecord


class ReviewRecordFilter(django_filters.FilterSet):
    published_at_after = django_filters.IsoDateTimeFilter(field_name="published_at", lookup_expr="gte")
    published_at_before = django_filters.IsoDateTimeFilter(field_name="published_at", lookup_expr="lte")

    class Meta:
        model = ReviewRecord
        fields = ("source", "product", "record_type", "author_role", "is_official")
