from django.utils import timezone
from rest_framework import serializers

from apps.analysis.models import AnalysisBatch, AnalysisEvaluation, AnalysisResult, AspectResult


class AspectResultSerializer(serializers.ModelSerializer):
    class Meta:
        model = AspectResult
        fields = (
            "id",
            "aspect",
            "sentiment",
            "sentiment_score",
            "issue_category",
            "issue_summary",
            "usage_scenario",
            "evidence_text",
            "context_dependent",
            "context_evidence_text",
            "context_evidence_review_id",
            "confidence",
        )


class AnalysisResultSerializer(serializers.ModelSerializer):
    aspects = AspectResultSerializer(many=True, read_only=True)
    review_id = serializers.IntegerField(source="review.id", read_only=True)
    record_type = serializers.CharField(source="review.record_type", read_only=True)
    original_title = serializers.CharField(source="review.title", read_only=True)
    original_content = serializers.CharField(source="review.content", read_only=True)
    published_at = serializers.DateTimeField(source="review.published_at", read_only=True)
    context_text = serializers.CharField(source="corpus_item.context_text", read_only=True, default="")
    evaluation = serializers.SerializerMethodField()

    def get_evaluation(self, obj: AnalysisResult) -> dict[str, object] | None:
        try:
            evaluation = obj.evaluation
        except AnalysisEvaluation.DoesNotExist:
            return None
        return AnalysisEvaluationSerializer(evaluation).data

    class Meta:
        model = AnalysisResult
        fields = (
            "id",
            "review_id",
            "record_type",
            "original_title",
            "original_content",
            "published_at",
            "context_text",
            "batch",
            "status",
            "provider",
            "model_name",
            "model_version",
            "prompt_version",
            "input_hash",
            "is_valid_content",
            "confidence",
            "summary",
            "raw_result",
            "error_code",
            "error_message",
            "attempt_count",
            "retry_count",
            "latency_ms",
            "prompt_tokens",
            "completion_tokens",
            "total_tokens",
            "analyzed_at",
            "aspects",
            "evaluation",
            "created_at",
            "updated_at",
        )


class AnalysisBatchSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)
    source_name = serializers.CharField(source="source.name", read_only=True)

    class Meta:
        model = AnalysisBatch
        fields = "__all__"
        read_only_fields = (
            "status",
            "success_count",
            "failed_count",
            "skipped_count",
            "retry_count",
            "prompt_tokens",
            "completion_tokens",
            "total_tokens",
            "started_at",
            "finished_at",
            "error_message",
        )


class AnalysisBatchCreateSerializer(serializers.Serializer):
    product_id = serializers.IntegerField()
    source_id = serializers.IntegerField()
    prompt_version = serializers.RegexField(r"^review_analysis_v\d+$", default="review_analysis_v2")
    limit = serializers.ChoiceField(choices=(20, 100, 278), default=20)
    force = serializers.BooleanField(default=False)
    retry_failed = serializers.BooleanField(default=False)


class AnalysisEvaluationSerializer(serializers.ModelSerializer):
    class Meta:
        model = AnalysisEvaluation
        fields = (
            "aspect_correct",
            "sentiment_correct",
            "issue_correct",
            "scenario_correct",
            "evidence_correct",
            "hallucination",
            "reviewer_notes",
            "evaluated_at",
        )
        read_only_fields = ("evaluated_at",)

    def create(self, validated_data: dict[str, object]) -> AnalysisEvaluation:
        validated_data["evaluated_at"] = timezone.now()
        return super().create(validated_data)

    def update(self, instance: AnalysisEvaluation, validated_data: dict[str, object]) -> AnalysisEvaluation:
        validated_data["evaluated_at"] = timezone.now()
        return super().update(instance, validated_data)
