from rest_framework.viewsets import ReadOnlyModelViewSet

from apps.sources.models import DataSource
from apps.sources.serializers import DataSourceSerializer


class DataSourceViewSet(ReadOnlyModelViewSet):
    queryset = DataSource.objects.prefetch_related("targets__product")
    serializer_class = DataSourceSerializer
    filterset_fields = ("source_type", "is_active")
    search_fields = ("name", "code")
    ordering_fields = ("name", "created_at")
