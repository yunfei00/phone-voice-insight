"""OpenAI-compatible chat completions provider implemented with httpx."""

# ruff: noqa: RUF001

from __future__ import annotations

import time
from typing import Any

import httpx

from ai.providers.base import AIProvider, AIProviderError, AIProviderResponse
from ai.schemas.review_analysis import ReviewAnalysisInput


class OpenAICompatibleProvider(AIProvider):
    provider_name = "openai_compatible"

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        timeout_seconds: int,
        temperature: float,
        max_output_tokens: int,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.temperature = temperature
        self.max_output_tokens = max_output_tokens

    def analyze_review(
        self,
        request: ReviewAnalysisInput,
        *,
        prompt: str,
        validation_feedback: str = "",
    ) -> AIProviderResponse:
        user_payload = request.model_dump_json(exclude_none=True)
        if validation_feedback:
            user_payload = f"上次输出未通过证据校验：{validation_feedback}\n请重新输出完整 JSON。\n输入：{user_payload}"
        started = time.perf_counter()
        try:
            response = httpx.post(
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                json={
                    "model": self.model,
                    "temperature": self.temperature,
                    "max_tokens": self.max_output_tokens,
                    "response_format": {"type": "json_object"},
                    "messages": [
                        {"role": "system", "content": prompt},
                        {"role": "user", "content": user_payload},
                    ],
                },
                timeout=self.timeout_seconds,
                follow_redirects=False,
            )
        except httpx.TimeoutException as exc:
            raise AIProviderError("AI_TIMEOUT", "AI request timed out", retriable=True) from exc
        except httpx.HTTPError as exc:
            raise AIProviderError("AI_PROVIDER_ERROR", "AI provider request failed", retriable=False) from exc
        latency_ms = round((time.perf_counter() - started) * 1000)
        if response.status_code == 429:
            raise AIProviderError("AI_RATE_LIMITED", "AI provider rate limited the request", retriable=True)
        if response.status_code >= 500:
            raise AIProviderError("AI_PROVIDER_5XX", "AI provider returned a server error", retriable=True)
        if response.status_code in {401, 403}:
            raise AIProviderError("AI_AUTHENTICATION_FAILED", "AI provider authentication failed")
        if response.status_code >= 400:
            raise AIProviderError("AI_PROVIDER_ERROR", f"AI provider returned HTTP {response.status_code}")
        try:
            payload: dict[str, Any] = response.json()
            content = str(payload["choices"][0]["message"]["content"])
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise AIProviderError("AI_RESPONSE_FORMAT_ERROR", "AI provider response shape is invalid") from exc
        usage_value = payload.get("usage")
        usage: dict[str, Any] = usage_value if isinstance(usage_value, dict) else {}
        return AIProviderResponse(
            provider=self.provider_name,
            model=self.model,
            content=content,
            latency_ms=latency_ms,
            prompt_tokens=_optional_int(usage.get("prompt_tokens")),
            completion_tokens=_optional_int(usage.get("completion_tokens")),
            total_tokens=_optional_int(usage.get("total_tokens")),
            request_id=response.headers.get("x-request-id", "")[:200],
        )


def _optional_int(value: object) -> int | None:
    return int(value) if isinstance(value, int) and value >= 0 else None
