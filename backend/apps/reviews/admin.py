from django.contrib import admin

from apps.reviews.models import AnalysisCorpusItem, ReviewQuality, ReviewQualityRun, ReviewRecord


@admin.register(ReviewRecord)
class ReviewRecordAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "source",
        "product",
        "record_type",
        "is_official",
        "rating",
        "published_at",
        "status",
    )
    list_filter = ("source", "product", "record_type", "is_official", "status")
    search_fields = ("external_id", "title", "content", "content_hash")
    readonly_fields = ("content_hash", "created_at", "updated_at")
    date_hierarchy = "published_at"


@admin.register(ReviewQuality)
class ReviewQualityAdmin(admin.ModelAdmin):
    list_display = (
        "review",
        "eligible_for_ai",
        "exclusion_reason",
        "quality_score",
        "manual_override",
        "processor_version",
        "processed_at",
    )
    list_filter = (
        "eligible_for_ai",
        "exclusion_reason",
        "is_official_content",
        "is_low_information",
        "is_navigation_or_page_noise",
        "is_promotional",
        "is_duplicate",
        "manual_override",
        "processor_version",
    )
    search_fields = ("review__external_id", "review__title", "review__content", "normalized_text")
    readonly_fields = (
        "review",
        "normalized_text",
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
        "created_at",
        "updated_at",
    )


@admin.register(ReviewQualityRun)
class ReviewQualityRunAdmin(admin.ModelAdmin):
    list_display = ("review", "processor_version", "eligible_for_ai", "exclusion_reason", "processed_at")
    list_filter = ("processor_version", "eligible_for_ai", "exclusion_reason")
    readonly_fields = (
        "review",
        "processor_version",
        "normalized_text",
        "eligible_for_ai",
        "exclusion_reason",
        "quality_score",
        "flags_json",
        "processed_at",
        "created_at",
        "updated_at",
    )


@admin.register(AnalysisCorpusItem)
class AnalysisCorpusItemAdmin(admin.ModelAdmin):
    list_display = ("review", "product", "source", "record_type", "eligible", "quality_score", "corpus_version")
    list_filter = ("eligible", "exclusion_reason", "record_type", "author_role", "source", "corpus_version")
    search_fields = ("review__external_id", "normalized_text", "context_text")
    readonly_fields = (
        "review",
        "quality",
        "product",
        "source",
        "record_type",
        "author_role",
        "normalized_text",
        "context_text",
        "eligible",
        "exclusion_reason",
        "quality_score",
        "corpus_version",
        "created_at",
        "updated_at",
    )
