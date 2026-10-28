from rest_framework import serializers

from apps.collection.models import CollectionRun, CollectionSchedule, CollectionTargetState, CollectionTask
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
            "completion_verified",
            "verification_report",
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
            "trigger_type",
            "status",
            "requested_limit",
            "requested_pages",
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
            "completion_verified",
            "verification_report",
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
            "completion_verified",
            "verification_report",
        )

    def validate_source_target(self, value: SourceTarget) -> SourceTarget:
        if not value.is_active:
            raise serializers.ValidationError("不能为停用的采集入口创建任务")
        return value

    def validate(self, attrs: dict) -> dict:
        pages = attrs.get("requested_pages")
        if pages is not None and not 1 <= pages <= 1000:
            raise serializers.ValidationError({"requested_pages": "采集页数必须在 1 至 1000 之间"})
        if attrs.get("task_type") == "FULL":
            attrs["requested_limit"] = None
        return attrs


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


class CollectionTargetStateSerializer(serializers.ModelSerializer):
    source_target = serializers.IntegerField(source="source_target_id", read_only=True)
    source_id = serializers.IntegerField(source="source_target.source_id", read_only=True)
    source_code = serializers.CharField(source="source_target.source.code", read_only=True)
    source_name = serializers.CharField(source="source_target.source.name", read_only=True)
    product_id = serializers.IntegerField(source="source_target.product_id", read_only=True)
    product_name = serializers.CharField(source="source_target.product.name", read_only=True)
    target_name = serializers.CharField(source="source_target.name", read_only=True)
    target_url = serializers.CharField(source="source_target.target_url", read_only=True)
    active_task_status = serializers.CharField(source="active_task.status", read_only=True, allow_null=True)
    schedule_id = serializers.SerializerMethodField()
    schedule_enabled = serializers.SerializerMethodField()
    schedule_interval_hours = serializers.SerializerMethodField()
    has_historical_data = serializers.BooleanField(read_only=True)
    validation_status = serializers.CharField(source="source_target.validation_status", read_only=True)
    validated_at = serializers.DateTimeField(source="source_target.validated_at", read_only=True)
    validation_error_message = serializers.CharField(source="source_target.validation_error_message", read_only=True)
    last_task_type = serializers.SerializerMethodField()
    last_task_status = serializers.SerializerMethodField()
    last_new_threads = serializers.SerializerMethodField()
    last_new_replies = serializers.SerializerMethodField()
    last_failure_count = serializers.SerializerMethodField()
    progress_stage = serializers.SerializerMethodField()

    class Meta:
        model = CollectionTargetState
        fields = (
            "id",
            "source_target",
            "source_id",
            "source_code",
            "source_name",
            "product_id",
            "product_name",
            "target_name",
            "target_url",
            "status",
            "full_verified",
            "full_verified_at",
            "active_task",
            "active_task_status",
            "last_full_task",
            "last_incremental_task",
            "last_success_at",
            "last_failure_at",
            "last_discovered_thread_count",
            "last_verified_thread_count",
            "last_error",
            "schedule_id",
            "schedule_enabled",
            "schedule_interval_hours",
            "has_historical_data",
            "validation_status",
            "validated_at",
            "validation_error_message",
            "last_task_type",
            "last_task_status",
            "last_new_threads",
            "last_new_replies",
            "last_failure_count",
            "progress_stage",
        )

    def _last_task(self, instance: CollectionTargetState) -> CollectionTask | None:
        tasks = [
            task for task in (instance.active_task, instance.last_full_task, instance.last_incremental_task) if task
        ]
        return max(tasks, key=lambda task: task.created_at) if tasks else None

    def get_last_task_type(self, instance: CollectionTargetState) -> str | None:
        task = self._last_task(instance)
        return task.task_type if task else None

    def get_last_task_status(self, instance: CollectionTargetState) -> str | None:
        task = self._last_task(instance)
        return task.status if task else None

    def get_last_new_threads(self, instance: CollectionTargetState) -> int:
        task = self._last_task(instance)
        return task.new_threads if task else 0

    def get_last_new_replies(self, instance: CollectionTargetState) -> int:
        task = self._last_task(instance)
        return max(task.new_records - task.new_threads, 0) if task else 0

    def get_last_failure_count(self, instance: CollectionTargetState) -> int:
        task = self._last_task(instance)
        return task.failure_count if task else 0

    def get_progress_stage(self, instance: CollectionTargetState) -> str:
        if not instance.active_task:
            return ""
        return str(instance.active_task.last_checkpoint.get("phase", "pending"))

    def _schedule(self, instance: CollectionTargetState) -> CollectionSchedule | None:
        try:
            return instance.source_target.collection_schedule
        except CollectionSchedule.DoesNotExist:
            return None

    def get_schedule_id(self, instance: CollectionTargetState) -> int | None:
        schedule = self._schedule(instance)
        return schedule.id if schedule else None

    def get_schedule_enabled(self, instance: CollectionTargetState) -> bool:
        schedule = self._schedule(instance)
        return bool(schedule and schedule.enabled)

    def get_schedule_interval_hours(self, instance: CollectionTargetState) -> int | None:
        schedule = self._schedule(instance)
        return schedule.interval_hours if schedule else None
