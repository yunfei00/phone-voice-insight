from rest_framework import serializers

from apps.collection.models import CollectionStatus, CollectionTargetState, CollectionTargetStatus
from apps.sources.models import DataSource, SourceTarget


class SourceTargetSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)

    class Meta:
        model = SourceTarget
        fields = (
            "id",
            "product",
            "source",
            "product_name",
            "name",
            "target_type",
            "target_url",
            "external_id",
            "config_json",
            "is_active",
            "validation_status",
            "validated_at",
            "validation_error_code",
            "validation_error_message",
            "validation_report",
        )
        read_only_fields = (
            "validation_status",
            "validated_at",
            "validation_error_code",
            "validation_error_message",
            "validation_report",
        )

    def update(self, instance: SourceTarget, validated_data: dict[str, object]) -> SourceTarget:
        old_url = instance.target_url
        new_url = str(validated_data.get("target_url", old_url))
        if (
            new_url != old_url
            and instance.collection_tasks.filter(
                status__in=(CollectionStatus.PENDING, CollectionStatus.RUNNING, CollectionStatus.PAUSED)
            ).exists()
        ):
            raise serializers.ValidationError({"target_url": "采集任务运行中; 不能修改入口网址"})
        target = super().update(instance, validated_data)
        if new_url != old_url:
            target.validation_status = "UNVERIFIED"
            target.validated_at = None
            target.validated_url_hash = ""
            target.validation_error_code = ""
            target.validation_error_message = ""
            target.validation_report = {}
            target.save(
                update_fields=(
                    "validation_status",
                    "validated_at",
                    "validated_url_hash",
                    "validation_error_code",
                    "validation_error_message",
                    "validation_report",
                    "updated_at",
                )
            )
            state, _ = CollectionTargetState.objects.get_or_create(source_target=target)
            state.full_verified = False
            state.full_verified_at = None
            state.status = CollectionTargetStatus.NOT_INITIALIZED
            state.last_error = "采集入口网址已变更; 需要重新验证并建立全量基线"
            state.save(update_fields=("full_verified", "full_verified_at", "status", "last_error", "updated_at"))
        return target


class DataSourceSerializer(serializers.ModelSerializer):
    targets = SourceTargetSerializer(many=True, read_only=True)

    class Meta:
        model = DataSource
        fields = ("id", "code", "name", "source_type", "is_active", "targets")
