from rest_framework import serializers

from apps.sources.models import DataSource, SourceTarget


class SourceTargetSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)

    class Meta:
        model = SourceTarget
        fields = (
            "id",
            "product",
            "product_name",
            "name",
            "target_type",
            "target_url",
            "external_id",
            "is_active",
        )


class DataSourceSerializer(serializers.ModelSerializer):
    targets = SourceTargetSerializer(many=True, read_only=True)

    class Meta:
        model = DataSource
        fields = ("id", "code", "name", "source_type", "is_active", "targets")
