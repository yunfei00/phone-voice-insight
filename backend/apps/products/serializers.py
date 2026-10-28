from rest_framework import serializers
import re
import unicodedata

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
    brand_id = serializers.PrimaryKeyRelatedField(source='brand', queryset=Brand.objects.all(), write_only=True)
    aliases = ProductAliasSerializer(many=True, read_only=True)
    variants = ProductVariantSerializer(many=True, read_only=True)
    normalized_name = serializers.CharField(read_only=True)
    series = serializers.CharField(required=False, allow_blank=True)
    model_code = serializers.CharField(required=False, allow_blank=True)

    def validate(self, attrs):
        brand = attrs.get('brand', getattr(self.instance, 'brand', None))
        name = attrs.get('name', getattr(self.instance, 'name', '')).strip()
        if not name:
            raise serializers.ValidationError({'name': '手机名称不能为空'})
        if brand and Product.objects.filter(brand=brand, name__iexact=name).exclude(pk=getattr(self.instance, 'pk', None)).exists():
            raise serializers.ValidationError({'name': '该品牌下已存在同名手机'})
        if not self.instance:
            normalized = unicodedata.normalize('NFKC', name).casefold()
            normalized = re.sub(r'\\s+', '', normalized)
            if Product.objects.filter(normalized_name=normalized).exists():
                raise serializers.ValidationError({'name': '已存在相同标准名称的手机'})
            attrs['normalized_name'] = normalized
        return attrs

    def create(self, validated_data):
        validated_data.setdefault('series', '')
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
