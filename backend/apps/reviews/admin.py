from django.contrib import admin

from apps.reviews.models import ReviewRecord


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
