from rest_framework.viewsets import ReadOnlyModelViewSet

from apps.analysis.models import AnalysisResult
from apps.analysis.serializers import AnalysisResultSerializer


class AnalysisResultViewSet(ReadOnlyModelViewSet):
    queryset = AnalysisResult.objects.select_related("review").prefetch_related("aspects")
    serializer_class = AnalysisResultSerializer
    filterset_fields = ("status", "model_name", "is_valid_content", "review")
    search_fields = ("summary", "review__content")
    ordering_fields = ("analyzed_at", "created_at", "confidence")
