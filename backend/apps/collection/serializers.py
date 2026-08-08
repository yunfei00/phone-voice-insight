from rest_framework import serializers

from apps.collection.models import CollectionRun, CollectionTask
from apps.sources.models import SourceTarget


class CollectionRunSerializer(serializers.ModelSerializer):
    class Meta:
        model = CollectionRun
        fields = (
            "id",
            "run_number",
            "status",
            "started_at",
            "finished_at",
            "success_count",
            "skipped_count",
            "failure_count",
            "new_threads",
            "known_threads",
            "new_records",
            "duplicate_records",
            "stopped_at_known_boundary",
            "checkpoint_json",
            "error_message",
        )


class CollectionTaskSerializer(serializers.ModelSerializer):
    source_name = serializers.CharField(source="source_target.source.name", read_only=True)
    product_name = serializers.CharField(source="source_target.product.name", read_only=True)
    target_name = serializers.CharField(source="source_target.name", read_only=True)
    runs = CollectionRunSerializer(many=True, read_only=True)

    class Meta:
        model = CollectionTask
        fields = (
            "id",
            "source_target",
            "source_name",
            "product_name",
            "target_name",
            "task_type",
            "status",
            "requested_limit",
            "started_at",
            "finished_at",
            "last_checkpoint",
            "success_count",
            "skipped_count",
            "failure_count",
            "new_threads",
            "known_threads",
            "new_records",
            "duplicate_records",
            "stopped_at_known_boundary",
            "error_message",
            "runs",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "status",
            "started_at",
            "finished_at",
            "last_checkpoint",
            "success_count",
            "skipped_count",
            "failure_count",
            "new_threads",
            "known_threads",
            "new_records",
            "duplicate_records",
            "stopped_at_known_boundary",
            "error_message",
        )

    def validate_source_target(self, value: SourceTarget) -> SourceTarget:
        if not value.is_active:
            raise serializers.ValidationError("不能为停用的采集入口创建任务")
        return value
