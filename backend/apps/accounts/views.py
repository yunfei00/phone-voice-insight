from typing import Any, cast

import httpx
from ai.providers import AIProviderError
from django.contrib.auth import get_user_model
from django.contrib.auth.models import User as DjangoUser
from django.db import transaction
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.serializers import BaseSerializer
from rest_framework.views import APIView
from rest_framework.viewsets import ModelViewSet

from apps.accounts.ai_service import get_user_ai_provider
from apps.accounts.models import UserAIConfiguration, UserProfile, UserRole
from apps.accounts.permissions import IsAdministrator, IsAnalystOrAdministrator, get_user_role
from apps.accounts.serializers import (
    LoginSerializer,
    PasswordChangeSerializer,
    UserAIConfigurationSerializer,
    UserSerializer,
)

User = get_user_model()


@api_view(["POST"])
@permission_classes([AllowAny])
def login(request: Request) -> Response:
    serializer = LoginSerializer(data=request.data, context={"request": request})
    serializer.is_valid(raise_exception=True)
    user = serializer.validated_data["user"]
    token, _ = Token.objects.get_or_create(user=user)
    return Response({"token": token.key, "user": UserSerializer(user).data})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def logout(request: Request) -> Response:
    user = cast(DjangoUser, request.user)
    Token.objects.filter(user=user).delete()
    return Response(status=status.HTTP_204_NO_CONTENT)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def me(request: Request) -> Response:
    return Response(UserSerializer(request.user).data)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def change_password(request: Request) -> Response:
    serializer = PasswordChangeSerializer(data=request.data, context={"request": request})
    serializer.is_valid(raise_exception=True)
    user = cast(DjangoUser, request.user)
    user.set_password(serializer.validated_data["new_password"])
    user.save(update_fields=("password",))
    Token.objects.filter(user=user).delete()
    token = Token.objects.create(user=user)
    return Response({"token": token.key})


class UserViewSet(ModelViewSet):
    queryset = User.objects.select_related("profile").order_by("-date_joined")
    serializer_class = UserSerializer
    permission_classes = (IsAdministrator,)
    search_fields = ("username", "email", "first_name", "last_name")
    ordering_fields = ("username", "date_joined", "last_login")

    def perform_update(self, serializer: BaseSerializer[Any]) -> None:
        user_serializer = cast(UserSerializer, serializer)
        target = self.get_object()
        role = user_serializer.validated_data.get("role", get_user_role(target))
        active = user_serializer.validated_data.get("is_active", target.is_active)
        if target.pk == self.request.user.pk and (role != UserRole.ADMIN or not active):
            from rest_framework.exceptions import ValidationError

            raise ValidationError("不能停用当前账号或取消其管理员角色。")
        self._protect_last_admin(target, role=role, active=active)
        user = user_serializer.save()
        if not user.is_active:
            Token.objects.filter(user=user).delete()

    def perform_destroy(self, instance: object) -> None:
        if getattr(instance, "pk", None) == self.request.user.pk:
            from rest_framework.exceptions import ValidationError

            raise ValidationError("不能删除当前登录账号。")
        self._protect_last_admin(instance, role=UserRole.VIEWER, active=False)
        super().perform_destroy(instance)

    @action(detail=True, methods=("post",), url_path="reset-password")
    def reset_password(self, request: Request, pk: str | None = None) -> Response:
        del pk
        user = self.get_object()
        if user.pk == request.user.pk:
            from rest_framework.exceptions import ValidationError

            raise ValidationError("请使用“修改密码”功能更新当前账号密码。")
        password = request.data.get("password", "")
        from django.contrib.auth import password_validation
        from rest_framework.exceptions import ValidationError

        try:
            password_validation.validate_password(password, user)
        except Exception as exc:
            raise ValidationError({"password": list(getattr(exc, "messages", [str(exc)]))}) from exc
        user.set_password(password)
        user.save(update_fields=("password",))
        Token.objects.filter(user=user).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @staticmethod
    def _protect_last_admin(target: object, *, role: str, active: bool) -> None:
        if get_user_role(target) != UserRole.ADMIN or (role == UserRole.ADMIN and active):
            return
        with transaction.atomic():
            admin_count = (
                UserProfile.objects.select_for_update().filter(role=UserRole.ADMIN, user__is_active=True).count()
            )
            if admin_count <= 1:
                from rest_framework.exceptions import ValidationError

                raise ValidationError("系统必须至少保留一个启用的管理员账号。")


class UserAIConfigurationView(APIView):
    permission_classes = (IsAnalystOrAdministrator,)

    def get(self, request: Request) -> Response:
        user = cast(DjangoUser, request.user)
        configuration = UserAIConfiguration.objects.filter(user=user).first()
        if configuration is None:
            configuration = UserAIConfiguration(user=user)
        return Response(UserAIConfigurationSerializer(configuration).data)

    def put(self, request: Request) -> Response:
        return self._save(request, partial=False)

    def patch(self, request: Request) -> Response:
        return self._save(request, partial=True)

    def delete(self, request: Request) -> Response:
        user = cast(DjangoUser, request.user)
        UserAIConfiguration.objects.filter(user=user).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @staticmethod
    def _save(request: Request, *, partial: bool) -> Response:
        user = cast(DjangoUser, request.user)
        configuration = UserAIConfiguration.objects.filter(user=user).first()
        serializer = UserAIConfigurationSerializer(
            configuration,
            data=request.data,
            partial=partial,
        )
        serializer.is_valid(raise_exception=True)
        saved = serializer.save(user=user)
        return Response(UserAIConfigurationSerializer(saved).data)


class UserAIConnectivityView(APIView):
    permission_classes = (IsAnalystOrAdministrator,)

    def post(self, request: Request) -> Response:
        user = cast(DjangoUser, request.user)
        try:
            result = get_user_ai_provider(user).check_connectivity()
        except AIProviderError as exc:
            return Response(
                {"status": "error", "error_code": exc.code},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(
            {
                "status": "ok",
                "provider": result.provider,
                "model": result.model,
                "latency_ms": result.latency_ms,
            }
        )


class OllamaModelsView(APIView):
    permission_classes = (IsAnalystOrAdministrator,)

    def get(self, request: Request) -> Response:
        from urllib.parse import urlsplit

        configuration = UserAIConfiguration.objects.filter(user=request.user, provider="ollama").first()
        if configuration is None:
            return Response({"error_code": "OLLAMA_NOT_CONFIGURED"}, status=status.HTTP_400_BAD_REQUEST)
        base_url = configuration.base_url.rstrip("/")
        parsed = urlsplit(base_url)
        if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password:
            return Response({"error_code": "INVALID_OLLAMA_URL"}, status=status.HTTP_400_BAD_REQUEST)
        root = base_url[:-3] if base_url.endswith("/v1") else base_url
        try:
            response = httpx.get(f"{root}/api/tags", timeout=8, follow_redirects=False, trust_env=False)
            response.raise_for_status()
            payload = response.json()
            models = sorted(
                {
                    item["name"]
                    for item in payload.get("models", [])
                    if isinstance(item, dict) and isinstance(item.get("name"), str)
                }
            )
        except (httpx.HTTPError, ValueError, TypeError, KeyError):
            return Response({"error_code": "OLLAMA_UNREACHABLE"}, status=status.HTTP_502_BAD_GATEWAY)
        return Response({"models": models})
