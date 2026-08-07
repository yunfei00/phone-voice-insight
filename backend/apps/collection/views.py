from rest_framework.mixins import CreateModelMixin, ListModelMixin, RetrieveModelMixin
from rest_framework.viewsets import GenericViewSet

from apps.collection.models import CollectionTask
from apps.collection.serializers import CollectionTaskSerializer


class CollectionTaskViewSet(CreateModelMixin, ListModelMixin, RetrieveModelMixin, GenericViewSet):
    queryset = CollectionTask.objects.select_related(
        "source_target__source",
        "source_target__product",
    ).prefetch_related("runs")
    serializer_class = CollectionTaskSerializer
    filterset_fields = ("status", "task_type", "source_target", "source_target__source")
    search_fields = ("source_target__name", "source_target__product__name", "error_message")
    ordering_fields = ("created_at", "started_at", "finished_at", "status")
