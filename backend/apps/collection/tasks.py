"""Celery 采集任务入口。"""

from dataclasses import asdict
from typing import Any

from celery import Task, shared_task

from apps.collection.services.collection_runner import run_collection


@shared_task(name="system_ping")
def system_ping() -> dict[str, str]:
    return {"status": "ok"}


@shared_task(bind=True, name="run_collection_task")
def run_collection_task(self: Task, task_id: int) -> dict[str, Any]:  # noqa: ARG001
    return asdict(run_collection(task_id))
