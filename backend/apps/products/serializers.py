import re
import unicodedata
from typing import Any, cast

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
    brand_id = serializers.PrimaryKeyRelatedField(source="brand", queryset=Brand.objects.all(), write_only=True)
    aliases = ProductAliasSerializer(many=True, read_only=True)
    variants = ProductVariantSerializer(many=True, read_only=True)
    normalized_name = serializers.CharField(read_only=True)
    series = serializers.CharField(required=False, allow_blank=True)
    model_code = serializers.CharField(required=False, allow_blank=True)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        brand = attrs.get("brand", getattr(self.instance, "brand", None))
        name = attrs.get("name", getattr(self.instance, "name", "")).strip()
        if not name:
            raise serializers.ValidationError({"name": "手机名称不能为空"})
        same_name = Product.objects.filter(brand=brand, name__iexact=name) if brand else Product.objects.none()
        if self.instance is not None:
            same_name = same_name.exclude(pk=cast(int, self.instance.pk))
        if same_name.exists():
            raise serializers.ValidationError({"name": "该品牌下已存在同名手机"})
        identity = re.sub(r"\s+", "", unicodedata.normalize("NFKC", name)).casefold()
        brand_products = Product.objects.filter(brand=brand) if brand else Product.objects.none()
        if self.instance is not None:
            brand_products = brand_products.exclude(pk=cast(int, self.instance.pk))
        if brand and any(
            re.sub(r"\s+", "", unicodedata.normalize("NFKC", product.name)).casefold() == identity
            for product in brand_products
        ):
            raise serializers.ValidationError({"name": "该品牌下已存在名称等价的手机"})
        if not self.instance:
            normalized = identity
            if Product.objects.filter(normalized_name=normalized).exists():
                raise serializers.ValidationError({"name": "已存在相同标准名称的手机"})
            attrs["normalized_name"] = normalized
        return attrs

    def create(self, validated_data: dict[str, Any]) -> Product:
        validated_data.setdefault("series", "")
        return super().create(validated_data)

    class Meta:
        model = Product
        fields = (
            "id",
            "brand",
            "brand_id",
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
