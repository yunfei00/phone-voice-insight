from rest_framework import serializers

from apps.reviews.models import ReviewQuality, ReviewRecord


class ReviewRecordSerializer(serializers.ModelSerializer):
    source_name = serializers.CharField(source="source.name", read_only=True)
    product_name = serializers.CharField(source="product.name", read_only=True)
    variant_name = serializers.CharField(source="product_variant.sku_name", read_only=True, default=None)

    class Meta:
        model = ReviewRecord
        fields = (
            "id",
            "source",
            "source_name",
            "source_target",
            "product",
            "product_name",
            "product_variant",
            "variant_name",
            "external_id",
            "parent_external_id",
            "record_type",
            "title",
            "content",
            "rating",
            "published_at",
            "software_version",
            "author_role",
            "is_official",
            "is_append_review",
            "source_url",
            "content_hash",
            "raw_data",
            "status",
            "collected_at",
            "created_at",
            "updated_at",
        )


class ReviewQualitySerializer(serializers.ModelSerializer):
    review_id = serializers.IntegerField(source="review.id", read_only=True)
    source_id = serializers.IntegerField(source="review.source_id", read_only=True)
    source_name = serializers.CharField(source="review.source.name", read_only=True)
    product_id = serializers.IntegerField(source="review.product_id", read_only=True)
    product_name = serializers.CharField(source="review.product.name", read_only=True)
    record_type = serializers.CharField(source="review.record_type", read_only=True)
    author_role = serializers.CharField(source="review.author_role", read_only=True)
    original_title = serializers.CharField(source="review.title", read_only=True)
    original_content = serializers.CharField(source="review.content", read_only=True)
    published_at = serializers.DateTimeField(source="review.published_at", read_only=True)
    context_text = serializers.CharField(source="corpus_item.context_text", read_only=True, default="")

    class Meta:
        model = ReviewQuality
        fields = (
            "id",
            "review_id",
            "source_id",
            "source_name",
            "product_id",
            "product_name",
            "record_type",
            "author_role",
            "original_title",
            "original_content",
            "normalized_text",
            "context_text",
            "published_at",
            "has_meaningful_text",
            "is_product_related",
            "is_official_content",
            "is_low_information",
            "is_navigation_or_page_noise",
            "is_promotional",
            "is_duplicate",
            "duplicate_of",
            "eligible_for_ai",
            "exclusion_reason",
            "quality_score",
            "flags_json",
            "processor_version",
            "processed_at",
            "manual_override",
            "manual_eligible",
            "manual_reason",
            "created_at",
            "updated_at",
        )


class ReviewQualityOverrideSerializer(serializers.Serializer):
    eligible = serializers.BooleanField()
    reason = serializers.CharField(max_length=1000, allow_blank=False, trim_whitespace=True)
