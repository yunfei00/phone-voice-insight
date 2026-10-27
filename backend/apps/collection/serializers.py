from rest_framework import serializers

from apps.collection.models import CollectionRun, CollectionSchedule, CollectionTask
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


class CollectionScheduleSerializer(serializers.ModelSerializer):
    source_target = serializers.PrimaryKeyRelatedField(queryset=SourceTarget.objects.all(), validators=[])
    source_name = serializers.CharField(source="source_target.source.name", read_only=True)
    product_name = serializers.CharField(source="source_target.product.name", read_only=True)
    target_name = serializers.CharField(source="source_target.name", read_only=True)

    class Meta:
        model = CollectionSchedule
        fields = (
            "id",
            "source_target",
            "source_name",
            "product_name",
            "target_name",
            "enabled",
            "interval_hours",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("created_at", "updated_at")

    def validate_source_target(self, value: SourceTarget) -> SourceTarget:
        if not value.is_active:
            raise serializers.ValidationError("不能为停用的采集入口启用定时采集")
        return value

    def create(self, validated_data: dict) -> CollectionSchedule:
        source_target = validated_data.pop("source_target")
        schedule, _ = CollectionSchedule.objects.update_or_create(
            source_target=source_target,
            defaults=validated_data,
        )
        from apps.collection.services.schedule_service import sync_collection_schedule

        sync_collection_schedule(schedule)
        return schedule

    def update(self, instance: CollectionSchedule, validated_data: dict) -> CollectionSchedule:
        for name, value in validated_data.items():
            setattr(instance, name, value)
        instance.save()
        from apps.collection.services.schedule_service import sync_collection_schedule

        sync_collection_schedule(instance)
        return instance
