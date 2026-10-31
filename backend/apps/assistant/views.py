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
from django.db.models import Count, Max
from django.http import StreamingHttpResponse
from django.utils import timezone
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.renderers import JSONRenderer
from rest_framework.request import Request
from rest_framework.response import Response

from apps.accounts.permissions import IsAdministrator
from apps.assistant.models import (
    AssistantConversation,
    AssistantMessage,
    AssistantModelProfile,
    AssistantModelSelection,
    ConversationStatus,
    MessageStatus,
    RagDocument,
    RagIndexRun,
    RagIndexRunStatus,
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
from apps.assistant.tasks import run_rag_backfill
from apps.assistant.throttles import AssistantChatThrottle
from apps.reviews.models import RecordType, ReviewRecord


def _sse(event: dict[str, Any]) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False, default=str)}\n\n"


class RagSyncSerializer(serializers.Serializer):
    batch_size = serializers.IntegerField(default=100, min_value=1, max_value=500)


class AssistantModelProfileViewSet(viewsets.ModelViewSet):
    serializer_class = AssistantModelProfileSerializer
    permission_classes = (IsAdministrator,)

    def get_queryset(self):  # type: ignore[no-untyped-def]
        return AssistantModelProfile.objects.all()

    def list(self, request: Request, *args: Any, **kwargs: Any) -> Response:  # noqa: ARG002
        profiles = self.get_queryset()
        selection = AssistantModelSelection.objects.filter(slot="assistant").first()
        return Response(
            {
                "results": self.get_serializer(profiles, many=True).data,
                "assistant_model_id": selection.profile_id if selection else None,
            }
        )

    @action(detail=True, methods=("post",), url_path="duplicate")
    def duplicate(self, request: Request, pk: str | None = None) -> Response:  # noqa: ARG002
        source = self.get_object()
        data = request.data.copy()
        data["provider"] = source.provider
        data["base_url"] = source.base_url
        if not data.get("api_key") and source.api_key_ciphertext:
            data["api_key"] = source.get_api_key()
        serializer = self.get_serializer(data=data)
        serializer.is_valid(raise_exception=True)
        profile = serializer.save()
        return Response(self.get_serializer(profile).data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=("post",), url_path="select-assistant")
    def select_assistant(self, request: Request) -> Response:
        raw_id = request.data.get("model_id")
        if not isinstance(raw_id, int) or isinstance(raw_id, bool):
            return Response({"detail": "请选择已保存的模型。"}, status=status.HTTP_400_BAD_REQUEST)
        profile = self.get_queryset().filter(pk=raw_id, is_active=True).first()
        if profile is None:
            return Response({"detail": "模型不存在或已停用。"}, status=status.HTTP_400_BAD_REQUEST)
        AssistantModelSelection.objects.update_or_create(slot="assistant", defaults={"profile": profile})
        return Response({"assistant_model_id": profile.pk})

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

    @action(detail=False, methods=("post",), url_path="discover-models")
    def discover_models(self, request: Request) -> Response:
        provider = request.data.get("provider")
        if provider not in {"ollama", "openai_compatible"}:
            return Response({"detail": "不支持的服务类型。"}, status=status.HTTP_400_BAD_REQUEST)
        try:
            base_url = validate_ai_endpoint(str(request.data.get("base_url", "")), provider=provider)
            if provider == "ollama":
                root = base_url[:-3] if base_url.endswith("/v1") else base_url
                endpoint = f"{root}/api/tags"
                headers: dict[str, str] = {}
            else:
                key = str(request.data.get("api_key", "")).strip()
                if not key:
                    return Response({"detail": "请提供 API Key 或选择已有配置。"}, status=status.HTTP_400_BAD_REQUEST)
                root = base_url.rstrip("/")
                endpoint = f"{root}/models" if root.endswith("/v1") else f"{root}/v1/models"
                headers = {"Authorization": f"Bearer {key}"}
            response = httpx.get(endpoint, headers=headers, timeout=10, follow_redirects=False, trust_env=False)
            response.raise_for_status()
            payload = response.json()
            entries = payload.get("models", []) if provider == "ollama" else payload.get("data", [])
            models = sorted(
                {
                    value
                    for item in entries
                    if isinstance(item, dict)
                    for value in [item.get("name") if provider == "ollama" else item.get("id")]
                    if isinstance(value, str) and value
                }
            )
        except (httpx.HTTPError, ValueError, TypeError, KeyError):
            return Response(
                {"detail": "获取模型列表失败，请检查服务商接口或手动输入。"}, status=status.HTTP_502_BAD_GATEWAY
            )
        return Response({"models": models})

    @action(detail=True, methods=("get",), url_path="available-models")
    def available_models(self, request: Request, pk: str | None = None) -> Response:  # noqa: ARG002
        profile = self.get_object()
        if profile.provider not in {"ollama", "openai_compatible"}:
            return Response({"detail": "当前服务类型不支持模型列表发现。"}, status=status.HTTP_400_BAD_REQUEST)
        try:
            base_url = validate_ai_endpoint(profile.base_url, provider=profile.provider)
            if profile.provider == "ollama":
                root = base_url[:-3] if base_url.endswith("/v1") else base_url
                endpoint = f"{root}/api/tags"
                headers: dict[str, str] = {}
            else:
                endpoint = (
                    f"{base_url.rstrip('/')}/models"
                    if base_url.rstrip("/").endswith("/v1")
                    else f"{base_url.rstrip('/')}/v1/models"
                )
                headers = {"Authorization": f"Bearer {profile.get_api_key()}"}
            response = httpx.get(endpoint, headers=headers, timeout=10, follow_redirects=False, trust_env=False)
            response.raise_for_status()
            payload = response.json()
            entries = payload.get("models", []) if profile.provider == "ollama" else payload.get("data", [])
            models = sorted(
                {
                    value
                    for item in entries
                    if isinstance(item, dict)
                    for value in [item.get("name") if profile.provider == "ollama" else item.get("id")]
                    if isinstance(value, str) and value
                }
            )
        except (httpx.HTTPError, ValueError, TypeError, KeyError):
            return Response(
                {"detail": "获取模型列表失败；服务商可能不支持此接口，请手动输入模型名称。"},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        return Response({"models": models})

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


class RagIndexViewSet(viewsets.ViewSet):
    """Read index health; only administrators may start a historical backfill."""

    permission_classes = (IsAuthenticated,)

    def list(self, request: Request) -> Response:  # noqa: ARG002
        counts = {
            row["status"]: row["count"] for row in RagDocument.objects.values("status").annotate(count=Count("id"))
        }
        latest = RagDocument.objects.aggregate(value=Max("indexed_at"))["value"]
        thread_count = ReviewRecord.objects.filter(record_type=RecordType.THREAD).count()
        return Response(
            {
                "enabled": settings.RAG_INDEXING_ENABLED,
                "embedding_provider": settings.RAG_EMBEDDING_PROVIDER,
                "embedding_model": settings.RAG_EMBEDDING_MODEL,
                "thread_count": thread_count,
                "document_count": sum(counts.values()),
                "pending_count": max(thread_count - sum(counts.values()), 0),
                "status_counts": counts,
                "failed_count": counts.get("FAILED", 0),
                "last_synced_at": latest,
            }
        )

    @action(detail=False, methods=("post",), permission_classes=(IsAdministrator,))
    def sync(self, request: Request) -> Response:
        active = RagIndexRun.objects.filter(status__in=(RagIndexRunStatus.PENDING, RagIndexRunStatus.RUNNING)).first()
        if active:
            return Response({"detail": "已有索引任务正在执行", "run_id": active.id}, status=status.HTTP_409_CONFLICT)
        batch_size_serializer = RagSyncSerializer(data=request.data)
        batch_size_serializer.is_valid(raise_exception=True)
        run = RagIndexRun.objects.create(
            requested_count=ReviewRecord.objects.filter(record_type=RecordType.THREAD).count()
        )
        try:
            run_rag_backfill.delay(run.id, batch_size_serializer.validated_data["batch_size"])
        except Exception as exc:
            run.status = RagIndexRunStatus.FAILED
            run.error_message = "索引任务提交失败"
            run.finished_at = timezone.now()
            run.save()
            raise serializers.ValidationError("索引任务提交失败，请检查 Celery 服务。") from exc
        return Response({"run_id": run.id, "status": run.status}, status=status.HTTP_202_ACCEPTED)


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
