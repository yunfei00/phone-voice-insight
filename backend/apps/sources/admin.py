from django.contrib import admin

from apps.sources.models import DataSource, SourceTarget


class SourceTargetInline(admin.TabularInline):
    model = SourceTarget
    extra = 0


@admin.register(DataSource)
class DataSourceAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "source_type", "is_active")
    list_filter = ("source_type", "is_active")
    search_fields = ("name", "code")
    inlines = (SourceTargetInline,)


@admin.register(SourceTarget)
class SourceTargetAdmin(admin.ModelAdmin):
    list_display = ("name", "source", "product", "target_type", "is_active")
    list_filter = ("source", "target_type", "is_active")
    search_fields = ("name", "external_id", "product__name")
