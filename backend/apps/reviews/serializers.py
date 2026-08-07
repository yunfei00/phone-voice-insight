from rest_framework import serializers

from apps.reviews.models import ReviewRecord


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
