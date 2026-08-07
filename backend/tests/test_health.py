from unittest.mock import Mock, patch

import pytest
from django.urls import reverse
from rest_framework.test import APIClient


@pytest.mark.django_db
def test_health_reports_database_and_redis(api_client: APIClient) -> None:
    redis_client = Mock()
    redis_client.ping.return_value = True
    with patch("apps.common.views.get_redis_client", return_value=redis_client):
        response = api_client.get(reverse("health"))

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "phone-voice-insight-backend",
        "database": "ok",
        "redis": "ok",
    }
