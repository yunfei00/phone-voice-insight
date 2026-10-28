from django.db import transaction
from django.db.models import Exists, OuterRef
from django.utils import timezone
from datetime import timedelta
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.mixins import CreateModelMixin, ListModelMixin, RetrieveModelMixin
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet, ModelViewSet, ReadOnlyModelViewSet

from apps.collection.models import (
    CollectionSchedule,
    CollectionSourceLease,
    CollectionStatus,
    CollectionTargetState,
    CollectionTask,
    CollectionTaskType,
    CollectionTriggerType,
)
from apps.collection.serializers import (
    CollectionScheduleSerializer,
    CollectionTargetStateSerializer,
    CollectionTaskSerializer,
)
from apps.collection.services.orchestration import (
    CollectionAlreadyActive,
    claim_existing_task,
    release_source_lease,
    release_target,
    create_collection_task,
)
from apps.collection.tasks import run_collection_task
from apps.reviews.models import ReviewRecord


class CollectionTaskViewSet(CreateModelMixin, ListModelMixin, RetrieveModelMixin, GenericViewSet):
    queryset = CollectionTask.objects.select_related(
        "source_target__source",
        "source_target__product",
    ).prefetch_related("runs")
    serializer_class = CollectionTaskSerializer
    filterset_fields = ("status", "task_type", "source_target", "source_target__source")
    search_fields = ("source_target__name", "source_target__product__name", "error_message")
    ordering_fields = ("created_at", "started_at", "finished_at", "status")

    def create(self, request: Request, *args: object, **kwargs: object) -> Response:
        del args, kwargs
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            task = create_collection_task(
                source_target=serializer.validated_data["source_target"],
                task_type=serializer.validated_data.get("task_type", CollectionTaskType.INCREMENTAL),
                trigger_type=CollectionTriggerType.MANUAL,
                requested_limit=serializer.validated_data.get("requested_limit"),
            )
        except CollectionAlreadyActive as exc:
            return Response(
                {
                    "code": "COLLECTION_ALREADY_ACTIVE",
                    "detail": str(exc),
                    "active_task_id": exc.task_id,
                },
                status=status.HTTP_409_CONFLICT,
            )
        return Response(self.get_serializer(task).data, status=status.HTTP_201_CREATED)

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
            try:
                claim_existing_task(task)
            except CollectionAlreadyActive as exc:
                return Response(
                    {
                        "code": "COLLECTION_ALREADY_ACTIVE",
                        "detail": str(exc),
                        "active_task_id": exc.task_id,
                    },
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


    @action(detail=True, methods=("post",), url_path="recover-stale")
    def recover_stale(self, request: Request, pk: str | None = None) -> Response:
        """Explicit, guarded recovery: never override a live source lease."""
        del request, pk
        with transaction.atomic():
            task = CollectionTask.objects.select_for_update().select_related("source_target__source").get(
                pk=self.get_object().pk
            )
            if task.status not in (CollectionStatus.PENDING, CollectionStatus.RUNNING, CollectionStatus.PAUSED):
                return Response({"detail": "任务不是活动状态"}, status=status.HTTP_409_CONFLICT)
            if task.updated_at > timezone.now() - timedelta(minutes=15):
                return Response({"detail": "任务最近仍有更新，拒绝恢复"}, status=status.HTTP_409_CONFLICT)
            lease = CollectionSourceLease.objects.select_for_update().filter(
                source=task.source_target.source
            ).first()
            if lease and lease.owner_task_id == task.id and lease.expires_at and lease.expires_at > timezone.now():
                return Response({"detail": "来源租约仍有效，拒绝恢复"}, status=status.HTTP_409_CONFLICT)
            task.status = CollectionStatus.FAILED
            task.finished_at = timezone.now()
            task.error_message = "STALE_TASK_RECOVERY: 人工确认超时且无有效来源租约"
            task.save(update_fields=("status", "finished_at", "error_message", "updated_at"))
            task.runs.filter(status=CollectionStatus.RUNNING).update(
                status=CollectionStatus.FAILED, finished_at=timezone.now(),
                error_message=task.error_message,
            )
            release_source_lease(task.id)
            release_target(task, success=False, error=task.error_message)
        return Response(self.get_serializer(task).data)


class CollectionTargetStateViewSet(ReadOnlyModelViewSet):
    serializer_class = CollectionTargetStateSerializer
    queryset = (
        CollectionTargetState.objects.select_related(
            "source_target__source",
            "source_target__product",
            "source_target__collection_schedule",
            "active_task",
            "last_full_task",
            "last_incremental_task",
        )
        .annotate(
            has_historical_data=Exists(ReviewRecord.objects.filter(source_target_id=OuterRef("source_target_id")))
        )
        .filter(source_target__is_active=True)
    )
    filterset_fields = ("source_target__source", "source_target__product", "status", "full_verified")

    def _start(self, request: Request, task_type: str) -> Response:
        del request
        state = self.get_object()
        try:
            task = create_collection_task(
                source_target=state.source_target,
                task_type=task_type,
                trigger_type=CollectionTriggerType.MANUAL,
            )
        except CollectionAlreadyActive as exc:
            return Response(
                {
                    "code": "COLLECTION_ALREADY_ACTIVE",
                    "detail": str(exc),
                    "active_task_id": exc.task_id,
                },
                status=status.HTTP_409_CONFLICT,
            )
        async_result = run_collection_task.delay(task.id)
        return Response(
            {"task_id": task.id, "status": task.status, "celery_task_id": async_result.id},
            status=status.HTTP_202_ACCEPTED,
        )

    @action(detail=True, methods=("post",), url_path="start-full")
    def start_full(self, request: Request, pk: str | None = None) -> Response:
        del pk
        return self._start(request, CollectionTaskType.FULL)

    @action(detail=True, methods=("post",), url_path="start-incremental")
    def start_incremental(self, request: Request, pk: str | None = None) -> Response:
        del pk
        state = self.get_object()
        if not state.full_verified:
            return Response(
                {"code": "FULL_NOT_VERIFIED", "detail": "请先完成全量完整性校验"},
                status=status.HTTP_409_CONFLICT,
            )
        return self._start(request, CollectionTaskType.INCREMENTAL)


class CollectionScheduleViewSet(ModelViewSet):
    queryset = CollectionSchedule.objects.select_related(
        "source_target__source",
        "source_target__product",
    )
    serializer_class = CollectionScheduleSerializer
    filterset_fields = ("enabled", "source_target", "source_target__source", "source_target__product")

    def perform_destroy(self, instance: CollectionSchedule) -> None:
        from apps.collection.services.schedule_service import delete_collection_schedule

        delete_collection_schedule(instance)
        super().perform_destroy(instance)
