"""Celery 任务入口；当前阶段不执行真实网站采集。"""

from celery import Task, shared_task
from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from apps.collection.models import CollectionRun, CollectionStatus, CollectionTask


class CollectorNotImplementedError(RuntimeError):
    """目标来源的采集器尚未实现。"""


@shared_task(name="system_ping")
def system_ping() -> dict[str, str]:
    return {"status": "ok"}


@shared_task(bind=True, name="run_collection_task")
def run_collection_task(self: Task, task_id: int) -> None:  # noqa: ARG001
    with transaction.atomic():
        task = CollectionTask.objects.select_for_update().get(pk=task_id)
        task.transition_to(CollectionStatus.RUNNING)
        task.started_at = timezone.now()
        task.finished_at = None
        task.error_message = ""
        task.save(update_fields=("status", "started_at", "finished_at", "error_message", "updated_at"))
        latest_run = task.runs.aggregate(max_number=Max("run_number"))["max_number"] or 0
        run = CollectionRun.objects.create(
            task=task,
            run_number=latest_run + 1,
            status=CollectionStatus.RUNNING,
            started_at=task.started_at,
        )

    message = "collector not implemented"
    finished_at = timezone.now()
    with transaction.atomic():
        task = CollectionTask.objects.select_for_update().get(pk=task_id)
        task.transition_to(CollectionStatus.FAILED)
        task.finished_at = finished_at
        task.failure_count += 1
        task.error_message = message
        task.save(
            update_fields=(
                "status",
                "finished_at",
                "failure_count",
                "error_message",
                "updated_at",
            )
        )
        run.status = CollectionStatus.FAILED
        run.finished_at = finished_at
        run.failure_count = 1
        run.error_message = message
        run.save(update_fields=("status", "finished_at", "failure_count", "error_message"))

    raise CollectorNotImplementedError(message)
