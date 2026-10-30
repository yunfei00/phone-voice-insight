from __future__ import annotations

# ruff: noqa: RUF001
import json
from collections.abc import Iterator
from typing import Any, cast

import httpx
from ai.providers.base import AIProviderError
from django.conf import settings
from django.contrib.auth.models import User as DjangoUser
from django.core.cache import cache
from django.db.models import Count
from django.http import StreamingHttpResponse
from django.utils import timezone
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.renderers import JSONRenderer
from rest_framework.request import Request
from rest_framework.response import Response

from apps.accounts.models import UserAIConfiguration
from apps.assistant.models import (
    AssistantConversation,
    AssistantMessage,
    AssistantModelProfile,
    ConversationStatus,
    MessageStatus,
)
from apps.assistant.orchestrator import AssistantOrchestrator, prepare_chat, settings_from_profile
from apps.assistant.providers import AssistantProviderClient
from apps.assistant.renderers import EventStreamRenderer
from apps.assistant.security import validate_ai_endpoint
from apps.assistant.serializers import (
    AssistantChatRequestSerializer,
    AssistantConversationSerializer,
    AssistantMessageSerializer,
    AssistantModelProfileSerializer,
)
from apps.assistant.throttles import AssistantChatThrottle


def _sse(event: dict[str, Any]) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False, default=str)}\n\n"


class AssistantModelProfileViewSet(viewsets.ModelViewSet):
    serializer_class = AssistantModelProfileSerializer
    permission_classes = (IsAuthenticated,)

    def get_queryset(self):  # type: ignore[no-untyped-def]
        return AssistantModelProfile.objects.filter(user=cast(DjangoUser, self.request.user))

    def list(self, request: Request, *args: Any, **kwargs: Any) -> Response:  # noqa: ARG002
        profiles = self.get_queryset()
        default = UserAIConfiguration.objects.filter(user=cast(DjangoUser, request.user)).first()
        return Response(
            {
                "default_model": {
                    "id": None,
                    "name": "使用个人默认模型",
                    "model": default.model if default else "",
                    "provider": default.provider if default else "",
                    "configured": bool(default and default.is_configured),
                },
                "results": self.get_serializer(profiles, many=True).data,
            }
        )

    @action(detail=True, methods=("post",))
    def test(self, request: Request, pk: str | None = None) -> Response:  # noqa: ARG002
        profile = self.get_object()
        try:
            result = AssistantProviderClient(settings_from_profile(profile)).check_connectivity()
        except AIProviderError as exc:
            return Response(
                {"status": "error", "error_code": exc.code, "detail": exc.safe_message},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(result)

    @action(detail=True, methods=("get",), url_path="ollama-models")
    def ollama_models(self, request: Request, pk: str | None = None) -> Response:  # noqa: ARG002
        profile = self.get_object()
        if profile.provider != "ollama":
            return Response({"detail": "该配置不是 Ollama 模型。"}, status=status.HTTP_400_BAD_REQUEST)
        try:
            base_url = validate_ai_endpoint(profile.base_url, provider="ollama")
            root = base_url[:-3] if base_url.endswith("/v1") else base_url
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
            return Response({"detail": "无法读取 Ollama 模型，请检查服务地址。"}, status=status.HTTP_502_BAD_GATEWAY)
        return Response({"models": models})


class AssistantConversationViewSet(viewsets.ModelViewSet):
    serializer_class = AssistantConversationSerializer
    permission_classes = (IsAuthenticated,)

    def get_queryset(self):  # type: ignore[no-untyped-def]
        return (
            AssistantConversation.objects.filter(user=cast(DjangoUser, self.request.user))
            .select_related("model_profile")
            .annotate(message_count=Count("messages"))
            .order_by("-last_message_at", "-updated_at")
        )

    @action(detail=True, methods=("get",))
    def messages(self, request: Request, pk: str | None = None) -> Response:  # noqa: ARG002
        conversation = self.get_object()
        rows = conversation.messages.order_by("created_at")[: settings.ASSISTANT_MAX_MESSAGES_PER_CONVERSATION]
        return Response({"results": AssistantMessageSerializer(rows, many=True).data})

    @action(
        detail=True,
        methods=("post",),
        throttle_classes=(AssistantChatThrottle,),
        renderer_classes=(EventStreamRenderer, JSONRenderer),
    )
    def chat(self, request: Request, pk: str | None = None) -> Response | StreamingHttpResponse:  # noqa: ARG002
        conversation = self.get_object()
        serializer = AssistantChatRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data
        existing = AssistantMessage.objects.filter(conversation=conversation, request_id=payload["request_id"]).first()
        if existing:
            if existing.status == MessageStatus.COMPLETED:
                return _stream_replay(existing)
            return Response(
                {
                    "detail": "该请求已提交，当前状态不允许重复执行。",
                    "message_id": existing.id,
                    "status": existing.status,
                },
                status=status.HTTP_409_CONFLICT,
            )
        lock_key = f"assistant:user:{request.user.pk}:active"
        if not cache.add(lock_key, str(payload["request_id"]), timeout=settings.ASSISTANT_MAX_EXECUTION_SECONDS):
            return Response({"detail": "当前账号已有助手请求正在执行。"}, status=status.HTTP_429_TOO_MANY_REQUESTS)
        try:
            response_message, created = prepare_chat(
                conversation,
                request_id=payload["request_id"],
                content=payload["content"],
            )
        except RuntimeError as exc:
            cache.delete(lock_key)
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        if not created:
            cache.delete(lock_key)
            return Response({"detail": "该请求已存在。"}, status=status.HTTP_409_CONFLICT)
        filters = {
            key: value.isoformat() if hasattr(value, "isoformat") else value
            for key, value in payload.items()
            if key not in {"request_id", "content"} and value is not None
        }

        def stream() -> Iterator[str]:
            try:
                yield _sse({"type": "start", "message_id": str(response_message.id)})
                orchestrator = AssistantOrchestrator(conversation, response_message)
                for event in orchestrator.stream(payload["content"], filters):
                    yield _sse(event)
            except (AIProviderError, serializers.ValidationError, ValueError) as exc:
                code = exc.code if isinstance(exc, AIProviderError) else "ASSISTANT_MODEL_CONFIGURATION_INVALID"
                message = exc.safe_message if isinstance(exc, AIProviderError) else str(exc)
                AssistantMessage.objects.filter(pk=response_message.pk).update(
                    status=MessageStatus.FAILED,
                    error_code=code,
                    error_message=message[:500],
                    updated_at=timezone.now(),
                )
                AssistantConversation.objects.filter(pk=conversation.pk).update(
                    status=ConversationStatus.FAILED,
                    active_request_id=None,
                    updated_at=timezone.now(),
                )
                yield _sse({"type": "error", "code": code, "message": message})
            except GeneratorExit:
                AssistantMessage.objects.filter(pk=response_message.pk, status=MessageStatus.RUNNING).update(
                    status=MessageStatus.CANCELLED,
                    error_code="ASSISTANT_DISCONNECTED",
                    error_message="客户端连接已断开。",
                    updated_at=timezone.now(),
                )
                AssistantConversation.objects.filter(pk=conversation.pk, status=ConversationStatus.RUNNING).update(
                    status=ConversationStatus.CANCELLED,
                    active_request_id=None,
                    updated_at=timezone.now(),
                )
                raise
            finally:
                cache.delete(lock_key)

        response = StreamingHttpResponse(stream(), content_type="text/event-stream; charset=utf-8")
        response["Cache-Control"] = "no-cache, no-transform"
        response["X-Accel-Buffering"] = "no"
        return response

    @action(detail=True, methods=("post",))
    def cancel(self, request: Request, pk: str | None = None) -> Response:  # noqa: ARG002
        conversation = self.get_object()
        if conversation.status != ConversationStatus.RUNNING or not conversation.active_request_id:
            return Response({"status": conversation.status, "detail": "当前没有正在生成的回答。"})
        request_id = conversation.active_request_id
        AssistantConversation.objects.filter(pk=conversation.pk).update(
            status=ConversationStatus.CANCELLED,
            active_request_id=None,
            updated_at=timezone.now(),
        )
        AssistantMessage.objects.filter(request_id=request_id, status=MessageStatus.RUNNING).update(
            status=MessageStatus.CANCELLED,
            error_code="ASSISTANT_CANCELLED",
            error_message="用户已停止生成。",
            updated_at=timezone.now(),
        )
        cache.delete(f"assistant:user:{request.user.pk}:active")
        return Response({"status": ConversationStatus.CANCELLED, "request_id": request_id})


def _stream_replay(message: AssistantMessage) -> StreamingHttpResponse:
    def stream() -> Iterator[str]:
        yield _sse({"type": "start", "message_id": str(message.id), "replayed": True})
        if message.content:
            yield _sse({"type": "delta", "content": message.content})
        yield _sse({"type": "done", "message_id": str(message.id), "replayed": True})

    response = StreamingHttpResponse(stream(), content_type="text/event-stream; charset=utf-8")
    response["Cache-Control"] = "no-cache, no-transform"
    response["X-Accel-Buffering"] = "no"
    return response
