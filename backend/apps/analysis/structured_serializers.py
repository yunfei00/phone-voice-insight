from decimal import Decimal

from rest_framework import serializers

from apps.analysis.models import AnalysisBatch, AnalysisReviewRecord, AnalysisRun, OpinionAspect, StructuredAnalysis


class OpinionAspectSerializer(serializers.ModelSerializer):
    class Meta:
        model = OpinionAspect
        fields = "__all__"
        read_only_fields = ("analysis",)


class AnalysisReviewRecordSerializer(serializers.ModelSerializer):
    reviewer_name = serializers.CharField(source="reviewer.username", read_only=True)

    class Meta:
        model = AnalysisReviewRecord
        fields = "__all__"


class StructuredAnalysisSerializer(serializers.ModelSerializer):
    aspects = OpinionAspectSerializer(many=True, read_only=True)
    review_history = AnalysisReviewRecordSerializer(many=True, read_only=True)
    original_title = serializers.CharField(source="content.title", read_only=True)
    original_content = serializers.CharField(source="content.content", read_only=True)
    product_name = serializers.CharField(source="content.product.name", read_only=True)
    source_name = serializers.CharField(source="content.source.name", read_only=True)
    run_status = serializers.CharField(source="run.status", read_only=True)
    provider = serializers.CharField(source="run.provider", read_only=True)
    model = serializers.CharField(source="run.model", read_only=True)
    prompt_version = serializers.CharField(source="run.prompt_version", read_only=True)
    taxonomy_version = serializers.CharField(source="run.taxonomy_version", read_only=True)
    schema_version = serializers.CharField(source="run.schema_version", read_only=True)

    class Meta:
        model = StructuredAnalysis
        fields = "__all__"


class AnalysisRunSerializer(serializers.ModelSerializer):
    analysis_id = serializers.IntegerField(source="structured_analysis.id", read_only=True, default=None)
    content_excerpt = serializers.SerializerMethodField()

    def get_content_excerpt(self, obj: AnalysisRun) -> str:
        return obj.content.content[:120]

    class Meta:
        model = AnalysisRun
        fields = "__all__"


class ReviewCorrectionSerializer(serializers.Serializer):
    corrected_result = serializers.JSONField()
    review_reason = serializers.CharField(required=False, allow_blank=True, max_length=1000)


class StructuredBatchSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)
    source_name = serializers.CharField(source="source.name", read_only=True)

    class Meta:
        model = AnalysisBatch
        fields = "__all__"


class StructuredBatchCreateSerializer(serializers.Serializer):
    content_ids = serializers.ListField(child=serializers.IntegerField(min_value=1), required=False)
    product_id = serializers.IntegerField(required=False)
    source_id = serializers.IntegerField(required=False)
    published_at_after = serializers.DateTimeField(required=False)
    published_at_before = serializers.DateTimeField(required=False)
    max_items = serializers.IntegerField(min_value=1, max_value=1000, default=20)
    dry_run = serializers.BooleanField(default=True)
    max_concurrency = serializers.IntegerField(min_value=1, max_value=8, default=1)
    requests_per_minute = serializers.IntegerField(min_value=1, max_value=120, default=10)
    token_limit = serializers.IntegerField(min_value=1, required=False)
    cost_budget = serializers.DecimalField(max_digits=12, decimal_places=4, min_value=0, required=False)
    input_cost_per_million = serializers.DecimalField(max_digits=12, decimal_places=4, min_value=0, default=Decimal(0))
    output_cost_per_million = serializers.DecimalField(max_digits=12, decimal_places=4, min_value=0, default=Decimal(0))
    timeout_seconds = serializers.IntegerField(min_value=5, max_value=600, default=120)
    max_retries = serializers.IntegerField(min_value=0, max_value=3, default=1)

    def validate(self, attrs):  # type: ignore[no-untyped-def]
        if not attrs.get("content_ids") and not attrs.get("product_id") and not attrs.get("source_id"):
            raise serializers.ValidationError("content_ids、product_id、source_id 至少提供一项")
        return attrs
