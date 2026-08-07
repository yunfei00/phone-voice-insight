from django.contrib import admin

from apps.products.models import Brand, Product, ProductAlias, ProductVariant


class ProductAliasInline(admin.TabularInline):
    model = ProductAlias
    extra = 0


class ProductVariantInline(admin.TabularInline):
    model = ProductVariant
    extra = 0


@admin.register(Brand)
class BrandAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "is_active", "updated_at")
    list_filter = ("is_active",)
    search_fields = ("name", "code")


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("name", "brand", "series", "model_code", "is_active")
    list_filter = ("brand", "series", "is_active")
    search_fields = ("name", "normalized_name", "model_code")
    inlines = (ProductAliasInline, ProductVariantInline)


admin.site.register(ProductAlias)
admin.site.register(ProductVariant)
