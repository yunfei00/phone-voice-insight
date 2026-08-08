from django.db.models import Count
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.viewsets import ReadOnlyModelViewSet

from apps.reviews.filters import ReviewQualityFilter, ReviewRecordFilter
from apps.reviews.models import ExclusionReason, ReviewQuality, ReviewRecord
from apps.reviews.serializers import (
    ReviewQualityOverrideSerializer,
    ReviewQualitySerializer,
    ReviewRecordSerializer,
)
from apps.reviews.services.governance_pipeline import apply_manual_override, clear_manual_override


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


class ReviewQualityViewSet(ReadOnlyModelViewSet):
    queryset = ReviewQuality.objects.select_related(
        "review__source",
        "review__product",
        "duplicate_of",
        "corpus_item",
    )
    serializer_class = ReviewQualitySerializer
    filterset_class = ReviewQualityFilter
    search_fields = ("review__title", "review__content", "review__external_id", "normalized_text")
    ordering_fields = ("quality_score", "processed_at", "review__published_at", "review_id")

    @action(detail=False, methods=("get",))
    def summary(self, request: Request) -> Response:
        del request
        queryset = self.filter_queryset(self.get_queryset())
        total = queryset.count()
        eligible = queryset.filter(eligible_for_ai=True).count()
        exclusion_counts = {
            row["exclusion_reason"]: row["count"]
            for row in queryset.filter(eligible_for_ai=False).values("exclusion_reason").annotate(count=Count("id"))
        }
        category_filters = {
            "official": "is_official_content",
            "low_information": "is_low_information",
            "promotional": "is_promotional",
            "noise": "is_navigation_or_page_noise",
            "duplicate": "is_duplicate",
        }
        categories: dict[str, int] = {
            "product_not_matched": queryset.filter(is_product_related=False).count(),
            "empty": queryset.filter(normalized_text="").count(),
        }
        for name, field in category_filters.items():
            categories[name] = queryset.filter(**{field: True}).count()
        return Response(
            {
                "total": total,
                "eligible": eligible,
                "excluded": total - eligible,
                "eligibility_rate": round(eligible / total, 4) if total else 0.0,
                "categories": categories,
                "exclusion_reasons": {
                    reason.value: exclusion_counts.get(reason.value, 0) for reason in ExclusionReason
                },
            }
        )

    @action(detail=True, methods=("post",), url_path="override")
    def override(self, request: Request, pk: str | None = None) -> Response:
        del pk
        quality = self.get_object()
        serializer = ReviewQualityOverrideSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        apply_manual_override(
            quality.review_id,
            eligible=serializer.validated_data["eligible"],
            reason=serializer.validated_data["reason"],
        )
        quality.refresh_from_db()
        return Response(self.get_serializer(quality).data)

    @action(detail=True, methods=("post",), url_path="clear-override")
    def clear_override(self, request: Request, pk: str | None = None) -> Response:
        del request, pk
        quality = self.get_object()
        clear_manual_override(quality.review_id)
        quality.refresh_from_db()
        return Response(self.get_serializer(quality).data)
