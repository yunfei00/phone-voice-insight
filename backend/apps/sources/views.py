from rest_framework.viewsets import ModelViewSet, ReadOnlyModelViewSet
from django.db import transaction
from apps.collection.models import CollectionTargetState

from apps.sources.models import DataSource, SourceTarget
from apps.sources.serializers import DataSourceSerializer, SourceTargetSerializer


class DataSourceViewSet(ReadOnlyModelViewSet):
    queryset = DataSource.objects.prefetch_related("targets__product")
    serializer_class = DataSourceSerializer
    filterset_fields = ("source_type", "is_active")
    search_fields = ("name", "code")
    ordering_fields = ("name", "created_at")


class SourceTargetViewSet(ModelViewSet):
    queryset = SourceTarget.objects.select_related('product', 'source')
    serializer_class = SourceTargetSerializer
    filterset_fields = ('product', 'source', 'is_active')

    @transaction.atomic
    def perform_create(self, serializer):
        target = serializer.save()
        CollectionTargetState.objects.get_or_create(source_target=target)

    @transaction.atomic
    def perform_update(self, serializer):
        target = serializer.save()
        CollectionTargetState.objects.get_or_create(source_target=target)
