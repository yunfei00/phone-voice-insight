from django.contrib import admin

from apps.analysis.models import AnalysisResult, AspectResult


class AspectResultInline(admin.TabularInline):
    model = AspectResult
    extra = 0


@admin.register(AnalysisResult)
class AnalysisResultAdmin(admin.ModelAdmin):
    list_display = ("review", "status", "model_name", "model_version", "is_valid_content", "analyzed_at")
    list_filter = ("status", "is_valid_content", "model_name")
    search_fields = ("review__content", "summary", "model_name")
    inlines = (AspectResultInline,)


admin.site.register(AspectResult)
