import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import User
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from apps.accounts.models import UserProfile, UserRole

pytestmark = pytest.mark.django_db


def create_user(username: str, role: str, *, password: str = "ValidPass-2026") -> User:
    user = User.objects.create_user(username=username, password=password)
    UserProfile.objects.create(user=user, role=role)
    return user


def test_health_is_public_but_business_api_requires_login() -> None:
    client = APIClient()
    assert client.get("/api/v1/health/").status_code == 200
    assert client.get("/api/v1/products/").status_code == 401


def test_login_me_logout_flow() -> None:
    user = create_user("viewer", UserRole.VIEWER)
    client = APIClient()

    login_response = client.post(
        "/api/v1/auth/login/",
        {"username": "viewer", "password": "ValidPass-2026"},
        format="json",
    )
    assert login_response.status_code == 200
    assert login_response.data["user"]["role"] == UserRole.VIEWER
    token = login_response.data["token"]

    client.credentials(HTTP_AUTHORIZATION=f"Token {token}")
    assert client.get("/api/v1/auth/me/").data["username"] == "viewer"
    assert client.post("/api/v1/auth/logout/").status_code == 204
    assert not Token.objects.filter(user=user).exists()
    assert client.get("/api/v1/auth/me/").status_code == 401


def test_viewer_is_read_only() -> None:
    user = create_user("reader", UserRole.VIEWER)
    client = APIClient()
    client.force_authenticate(user=user)

    assert client.get("/api/v1/products/").status_code == 200
    assert client.post("/api/v1/collection-tasks/", {}, format="json").status_code == 403


def test_only_admin_can_manage_users() -> None:
    analyst = create_user("analyst", UserRole.ANALYST)
    client = APIClient()
    client.force_authenticate(user=analyst)
    assert client.get("/api/v1/users/").status_code == 403

    admin = create_user("admin", UserRole.ADMIN)
    client.force_authenticate(user=admin)
    response = client.post(
        "/api/v1/users/",
        {
            "username": "new-user",
            "password": "AnotherPass-2026",
            "role": UserRole.ANALYST,
            "is_active": True,
        },
        format="json",
    )
    assert response.status_code == 201
    created = get_user_model().objects.get(username="new-user")
    assert UserProfile.objects.get(user=created).role == UserRole.ANALYST


def test_admin_cannot_deactivate_or_demote_self() -> None:
    admin = create_user("admin", UserRole.ADMIN)
    client = APIClient()
    client.force_authenticate(user=admin)

    deactivate = client.patch(f"/api/v1/users/{admin.pk}/", {"is_active": False}, format="json")
    demote = client.patch(f"/api/v1/users/{admin.pk}/", {"role": UserRole.VIEWER}, format="json")
    assert deactivate.status_code == 400
    assert demote.status_code == 400
    admin.refresh_from_db()
    assert admin.is_active is True
    assert UserProfile.objects.get(user=admin).role == UserRole.ADMIN


def test_change_password_rotates_token() -> None:
    user = create_user("analyst", UserRole.ANALYST)
    old_token = Token.objects.create(user=user)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Token {old_token.key}")

    response = client.post(
        "/api/v1/auth/change-password/",
        {"old_password": "ValidPass-2026", "new_password": "ChangedPass-2026"},
        format="json",
    )
    assert response.status_code == 200
    assert response.data["token"] != old_token.key
    user.refresh_from_db()
    assert user.check_password("ChangedPass-2026")
