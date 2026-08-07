import pytest
from collectors.base import CollectorError
from django.core.exceptions import ValidationError
from rest_framework.test import APIClient

from apps.collection.models import CollectionStatus, CollectionTask
from apps.collection.tasks import run_collection_task, system_ping
from apps.sources.models import SourceTarget


@pytest.mark.django_db
def test_collection_task_status_transitions(source_target: SourceTarget) -> None:
    task = CollectionTask.objects.create(source_target=source_target)
    task.transition_to(CollectionStatus.RUNNING)
    assert task.status == CollectionStatus.RUNNING

    task.transition_to(CollectionStatus.SUCCESS)
    with pytest.raises(ValidationError):
        task.transition_to(CollectionStatus.RUNNING)


def test_system_ping_task() -> None:
    assert system_ping.run() == {"status": "ok"}


@pytest.mark.django_db
def test_collection_task_create_api(api_client: APIClient, source_target: SourceTarget) -> None:
    response = api_client.post(
        "/api/v1/collection-tasks/",
        {
            "source_target": source_target.id,
            "task_type": "INCREMENTAL",
            "requested_limit": 50,
        },
        format="json",
    )

    assert response.status_code == 201
    assert response.json()["status"] == CollectionStatus.PENDING
    assert CollectionTask.objects.filter(pk=response.json()["id"]).exists()


@pytest.mark.django_db
def test_unimplemented_jd_collection_task_is_persisted_as_failed(source_target: SourceTarget) -> None:
    task = CollectionTask.objects.create(source_target=source_target)

    with pytest.raises(CollectorError, match="not implemented"):
        run_collection_task.run(task.id)

    task.refresh_from_db()
    assert task.status == CollectionStatus.FAILED
    assert task.failure_count == 1
    assert task.runs.get().status == CollectionStatus.FAILED


@pytest.mark.django_db
def test_collection_task_run_api_queues_celery_task(
    api_client: APIClient,
    source_target: SourceTarget,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Result:
        id = "celery-test-id"

    task = CollectionTask.objects.create(source_target=source_target)
    monkeypatch.setattr("apps.collection.views.run_collection_task.delay", lambda _task_id: Result())

    response = api_client.post(f"/api/v1/collection-tasks/{task.id}/run/")

    assert response.status_code == 202
    assert response.json() == {
        "task_id": task.id,
        "status": CollectionStatus.PENDING,
        "celery_task_id": "celery-test-id",
    }
