from django.contrib import admin

from apps.collection.models import CollectionRun, CollectionTask


class CollectionRunInline(admin.TabularInline):
    model = CollectionRun
    extra = 0
    readonly_fields = ("run_number", "status", "started_at", "finished_at")


@admin.register(CollectionTask)
class CollectionTaskAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "source_target",
        "task_type",
        "status",
        "success_count",
        "failure_count",
        "created_at",
    )
    list_filter = ("status", "task_type", "source_target__source")
    search_fields = ("source_target__name", "error_message")
    readonly_fields = ("started_at", "finished_at", "last_checkpoint")
    inlines = (CollectionRunInline,)


@admin.register(CollectionRun)
class CollectionRunAdmin(admin.ModelAdmin):
    list_display = ("task", "run_number", "status", "started_at", "finished_at")
    list_filter = ("status",)
