from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass

import httpx
from django.conf import settings
from rest_framework.serializers import ValidationError

from apps.assistant.security import validate_ai_endpoint


class EmbeddingError(RuntimeError):
    pass


@dataclass(frozen=True)
class EmbeddingResult:
    vector: list[float]
    provider: str
    model: str


def _fake_embedding(text: str, dimensions: int) -> list[float]:
    """Deterministic test embedding; never selected by production defaults."""

    digest = hashlib.sha512(text.encode("utf-8")).digest()
    values = [((digest[index % len(digest)] / 255.0) * 2) - 1 for index in range(dimensions)]
    magnitude = math.sqrt(sum(item * item for item in values)) or 1
    return [item / magnitude for item in values]


def embed_text(text: str) -> EmbeddingResult | None:
    provider = settings.RAG_EMBEDDING_PROVIDER
    if provider == "disabled":
        return None
    dimensions = settings.RAG_EMBEDDING_DIMENSIONS
    if provider == "fake":
        if not settings.DEBUG and not settings.AI_ALLOW_FAKE_PROVIDER:
            raise EmbeddingError("生产环境不允许使用测试 Embedding Provider")
        return EmbeddingResult(_fake_embedding(text, dimensions), provider, settings.RAG_EMBEDDING_MODEL)
    if provider not in {"openai_compatible", "ollama"}:
        raise EmbeddingError("不支持的 Embedding Provider")
    try:
        base_url = validate_ai_endpoint(settings.RAG_EMBEDDING_BASE_URL, provider=provider)
    except ValidationError as exc:
        raise EmbeddingError(str(exc.detail)) from exc
    if provider == "ollama" and not base_url.endswith("/v1"):
        base_url += "/v1"
    headers = {"Content-Type": "application/json"}
    if settings.RAG_EMBEDDING_API_KEY:
        headers["Authorization"] = f"Bearer {settings.RAG_EMBEDDING_API_KEY}"
    try:
        response = httpx.post(
            f"{base_url}/embeddings",
            headers=headers,
            json={"model": settings.RAG_EMBEDDING_MODEL, "input": text},
            timeout=settings.RAG_EMBEDDING_TIMEOUT_SECONDS,
            follow_redirects=False,
            trust_env=False,
        )
        response.raise_for_status()
        vector = response.json()["data"][0]["embedding"]
    except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as exc:
        raise EmbeddingError("Embedding 服务请求失败") from exc
    if not isinstance(vector, list) or len(vector) != dimensions:
        raise EmbeddingError(f"Embedding 维度必须为 {dimensions}")
    try:
        normalized = [float(item) for item in vector]
    except (TypeError, ValueError) as exc:
        raise EmbeddingError("Embedding 返回了非数值向量") from exc
    return EmbeddingResult(normalized, provider, settings.RAG_EMBEDDING_MODEL)
