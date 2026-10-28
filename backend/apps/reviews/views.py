from django.db.models import Count, F, Sum
from rest_framework import serializers
from rest_framework.decorators import action
from rest_framework.permissions import IsAdminUser
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
from apps.reviews.services.governance_pipeline import apply_manual_override, clear_manual_override, process_reviews
from apps.reviews.services.metadata_completeness import metadata_completeness as build_metadata_completeness
from apps.reviews.services.thread_tree import (
    annotate_thread_metrics,
    build_reply_tree,
    filter_thread_search,
    replies_for_thread,
    serialize_reply_node,
    serialize_thread,
)
from apps.reviews.thread_serializers import ThreadTreeQuerySerializer


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
    ordering_fields = ("published_at", "collected_at", "created_at", "rating", "source__name", "product__name", "record_type", "content", "author_role", "source_region")

    @action(detail=False, methods=["get"])
    def facets(self, request: Request) -> Response:
        del request
        variants = list(
            ReviewRecord.objects.filter(product_variant__isnull=False)
            .values("product_variant_id", "product_variant__sku_name")
            .annotate(count=Count("id"))
            .order_by("product_variant_id")
        )
        regions = list(
            ReviewRecord.objects.exclude(source_region="")
            .values("source_region")
            .annotate(count=Count("id"))
            .order_by("source_region")
        )
        ratings = list(
            ReviewRecord.objects.filter(rating__isnull=False)
            .values("rating")
            .annotate(count=Count("id"))
            .order_by("-rating")
        )
        return Response({"variants": variants, "regions": regions, "ratings": ratings})

    @action(detail=False, methods=["get"], url_path="metadata-completeness")
    def metadata_completeness(self, request: Request) -> Response:
        del request
        return Response(build_metadata_completeness(self.filter_queryset(self.get_queryset())))


class ThreadTreeViewSet(ReadOnlyModelViewSet):
    """Paginated threads on list; a complete parent-linked reply tree on detail."""

    serializer_class = ReviewRecordSerializer
    queryset = ReviewRecord.objects.none()

    def list(self, request: Request) -> Response:
        query_data = request.query_params.copy()
        if source_value := request.query_params.get("source"):
            query_data["source_filter"] = source_value
        params = ThreadTreeQuerySerializer(data=query_data)
        params.is_valid(raise_exception=True)
        values = params.validated_data
        base = ReviewRecord.objects.filter(record_type="THREAD").select_related("product", "source")
        total_threads = base.count()
        if product := values.get("product"):
            base = base.filter(product_id=product)
        if source := str(values.get("source_filter", "")):
            base = base.filter(source_id=int(source)) if source.isdigit() else base.filter(source__code__iexact=source)
        queryset = annotate_thread_metrics(base)
        if published_after := values.get("published_at_after"):
            queryset = queryset.filter(published_at__gte=published_after)
        if published_before := values.get("published_at_before"):
            queryset = queryset.filter(published_at__lte=published_before)
        if activity_after := values.get("activity_at_after"):
            queryset = queryset.filter(activity_at__gte=activity_after)  # type: ignore[misc]
        if activity_before := values.get("activity_at_before"):
            queryset = queryset.filter(activity_at__lte=activity_before)  # type: ignore[misc]
        queryset = filter_thread_search(queryset, str(values.get("search", "")))
        ordering = {
            "latest_reply": (F("activity_at").desc(nulls_last=True), F("id").desc()),
            "latest_thread": (F("published_at").desc(nulls_last=True), F("id").desc()),
            "reply_count": (F("parsed_reply_count").desc(nulls_last=True), F("id").desc()),
            "view_count": (F("parsed_view_count").desc(nulls_last=True), F("id").desc()),
            "like_count": (F("parsed_like_count").desc(nulls_last=True), F("id").desc()),
        }[str(values["ordering"])]
        queryset = queryset.order_by(*ordering)
        matched_reply_count = queryset.aggregate(total=Sum("reply_match_count_safe"))["total"] or 0
        page = self.paginate_queryset(queryset)
        threads = list(page if page is not None else queryset)
        data = [serialize_thread(thread) for thread in threads]
        if page is None:
            return Response(
                {
                    "count": len(data),
                    "total_threads": total_threads,
                    "matched_reply_count": matched_reply_count,
                    "results": data,
                }
            )
        response = self.get_paginated_response(data)
        response.data["total_threads"] = total_threads
        response.data["matched_reply_count"] = matched_reply_count
        return response

    def retrieve(self, request: Request, pk: str | None = None) -> Response:
        del request
        thread = self.get_thread(pk)
        replies = replies_for_thread(thread)
        tree = build_reply_tree(thread, replies)
        return Response(
            {
                "thread": serialize_thread(thread),
                "replies": [serialize_reply_node(node) for node in tree],
            }
        )

    @staticmethod
    def get_thread(pk: str | None) -> ReviewRecord:
        from django.shortcuts import get_object_or_404

        queryset = annotate_thread_metrics(
            ReviewRecord.objects.filter(record_type="THREAD").select_related("product", "source")
        )
        return get_object_or_404(queryset, pk=pk)


class GovernanceBatchRequestSerializer(serializers.Serializer):
    product_id = serializers.IntegerField(min_value=1)
    source_id = serializers.IntegerField(min_value=1, required=False)
    limit = serializers.IntegerField(min_value=1, max_value=100, default=20)
    dry_run = serializers.BooleanField(default=True)
    reprocess = serializers.BooleanField(default=False)


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

    @action(detail=False, methods=("post",), url_path="process-batch", permission_classes=[IsAdminUser])
    def process_batch(self, request: Request) -> Response:
        """Run a bounded manual batch; dry-run by default."""
        params = GovernanceBatchRequestSerializer(data=request.data)
        params.is_valid(raise_exception=True)
        values = params.validated_data
        queryset = ReviewRecord.objects.filter(product_id=values["product_id"])
        if "source_id" in values:
            queryset = queryset.filter(source_id=values["source_id"])
        ids = list(queryset.order_by("id").values_list("id", flat=True)[: values["limit"]])
        result = process_reviews(
            ReviewRecord.objects.filter(id__in=ids),
            persist=not values["dry_run"],
            reprocess=values["reprocess"],
        )
        return Response({
            **result.as_dict(),
            "product_id": values["product_id"],
            "source_id": values.get("source_id"),
            "limit": values["limit"],
            "dry_run": values["dry_run"],
            "reprocess": values["reprocess"],
            "processed_review_ids": ids,
        })

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
