from rest_framework import serializers

from apps.analysis.models import AnalysisResult, AspectResult


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
            "confidence",
        )


class AnalysisResultSerializer(serializers.ModelSerializer):
    aspects = AspectResultSerializer(many=True, read_only=True)

    class Meta:
        model = AnalysisResult
        fields = (
            "id",
            "review",
            "status",
            "model_name",
            "model_version",
            "prompt_version",
            "is_valid_content",
            "confidence",
            "summary",
            "raw_result",
            "analyzed_at",
            "aspects",
            "created_at",
            "updated_at",
        )
