from rest_framework import serializers

from apps.products.models import Brand, Product, ProductAlias, ProductVariant


class BrandSerializer(serializers.ModelSerializer):
    class Meta:
        model = Brand
        fields = ("id", "name", "code", "is_active")


class ProductAliasSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductAlias
        fields = ("id", "alias", "normalized_alias", "source")


class ProductVariantSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductVariant
        fields = ("id", "memory", "storage", "color", "sku_name", "is_active")


class ProductSerializer(serializers.ModelSerializer):
    brand = BrandSerializer(read_only=True)
    aliases = ProductAliasSerializer(many=True, read_only=True)
    variants = ProductVariantSerializer(many=True, read_only=True)

    class Meta:
        model = Product
        fields = (
            "id",
            "brand",
            "name",
            "normalized_name",
            "series",
            "model_code",
            "release_date",
            "description",
            "is_active",
            "aliases",
            "variants",
            "created_at",
            "updated_at",
        )
