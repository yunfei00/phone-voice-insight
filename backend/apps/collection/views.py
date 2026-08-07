from django.db import transaction
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.mixins import CreateModelMixin, ListModelMixin, RetrieveModelMixin
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from apps.collection.models import CollectionStatus, CollectionTask
from apps.collection.serializers import CollectionTaskSerializer
from apps.collection.tasks import run_collection_task


class CollectionTaskViewSet(CreateModelMixin, ListModelMixin, RetrieveModelMixin, GenericViewSet):
    queryset = CollectionTask.objects.select_related(
        "source_target__source",
        "source_target__product",
    ).prefetch_related("runs")
    serializer_class = CollectionTaskSerializer
    filterset_fields = ("status", "task_type", "source_target", "source_target__source")
    search_fields = ("source_target__name", "source_target__product__name", "error_message")
    ordering_fields = ("created_at", "started_at", "finished_at", "status")

    @action(detail=True, methods=("post",))
    def run(self, request: Request, pk: str | None = None) -> Response:  # noqa: ARG002
        if pk is None:
            return Response({"detail": "缺少任务 ID"}, status=status.HTTP_404_NOT_FOUND)
        with transaction.atomic():
            task = CollectionTask.objects.select_for_update().get(pk=pk)
            if task.status in {
                CollectionStatus.RUNNING,
                CollectionStatus.PAUSED,
                CollectionStatus.CANCELLED,
            }:
                return Response(
                    {"detail": f"当前状态 {task.status} 不允许执行"},
                    status=status.HTTP_409_CONFLICT,
                )
            if task.status != CollectionStatus.PENDING:
                previous_status = task.status
                task.transition_to(CollectionStatus.PENDING)
                task.error_message = ""
                if previous_status == CollectionStatus.SUCCESS:
                    task.last_checkpoint = {}
                task.save(update_fields=("status", "error_message", "last_checkpoint", "updated_at"))

        async_result = run_collection_task.delay(task.id)
        return Response(
            {
                "task_id": task.id,
                "status": CollectionStatus.PENDING,
                "celery_task_id": async_result.id,
            },
            status=status.HTTP_202_ACCEPTED,
        )
