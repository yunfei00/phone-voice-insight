from django.contrib import admin

from apps.analysis.models import AnalysisBatch, AnalysisEvaluation, AnalysisResult, AspectResult


class AspectResultInline(admin.TabularInline):
    model = AspectResult
    extra = 0


@admin.register(AnalysisResult)
class AnalysisResultAdmin(admin.ModelAdmin):
    list_display = ("review", "status", "provider", "model_name", "prompt_version", "is_valid_content", "analyzed_at")
    list_filter = ("status", "provider", "is_valid_content", "model_name", "prompt_version")
    search_fields = ("review__content", "summary", "model_name")
    inlines = (AspectResultInline,)


admin.site.register(AspectResult)
admin.site.register(AnalysisBatch)
admin.site.register(AnalysisEvaluation)
