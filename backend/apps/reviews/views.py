from rest_framework.viewsets import ReadOnlyModelViewSet

from apps.reviews.filters import ReviewRecordFilter
from apps.reviews.models import ReviewRecord
from apps.reviews.serializers import ReviewRecordSerializer


class ReviewRecordViewSet(ReadOnlyModelViewSet):
    queryset = ReviewRecord.objects.select_related(
        "source",
        "source_target",
        "product",
        "product_variant",
    )
    serializer_class = ReviewRecordSerializer
    filterset_class = ReviewRecordFilter
    search_fields = ("title", "content", "external_id")
    ordering_fields = ("published_at", "collected_at", "created_at", "rating")
