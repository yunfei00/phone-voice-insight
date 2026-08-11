"""OpenAI-compatible chat completions provider implemented with httpx."""

# ruff: noqa: RUF001

from __future__ import annotations

import json
import time
from typing import Any

import httpx

from ai.providers.base import AIConnectivityResponse, AIProvider, AIProviderError, AIProviderResponse
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
        payload, latency_ms, request_id = self._chat_completion(
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": user_payload},
            ],
            max_tokens=self.max_output_tokens,
            temperature=self.temperature,
        )
        try:
            content = str(payload["choices"][0]["message"]["content"])
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise AIProviderError(
                "AI_RESPONSE_FORMAT_ERROR",
                "AI provider response shape is invalid",
                request_id=request_id,
            ) from exc
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
            request_id=request_id,
        )

    def check_connectivity(self) -> AIConnectivityResponse:
        payload, latency_ms, request_id = self._chat_completion(
            messages=[
                {
                    "role": "system",
                    "content": 'Return only valid JSON with exactly this object: {"status":"ok"}',
                },
                {"role": "user", "content": 'Return {"status":"ok"} now.'},
            ],
            max_tokens=32,
            temperature=0,
        )
        try:
            content = str(payload["choices"][0]["message"]["content"])
            parsed = _parse_json_object(content)
        except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise AIProviderError(
                "AI_RESPONSE_FORMAT_ERROR",
                "AI connectivity response is not valid JSON",
                request_id=request_id,
            ) from exc
        if parsed != {"status": "ok"}:
            raise AIProviderError(
                "AI_CONNECTIVITY_RESPONSE_INVALID",
                "AI connectivity response did not contain the expected status",
                request_id=request_id,
            )
        return AIConnectivityResponse(
            provider=self.provider_name,
            model=self.model,
            status="ok",
            latency_ms=latency_ms,
            request_id=request_id,
        )

    def _chat_completion(
        self,
        *,
        messages: list[dict[str, str]],
        max_tokens: int,
        temperature: float,
    ) -> tuple[dict[str, Any], int, str]:
        started = time.perf_counter()
        try:
            response = httpx.post(
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                json={
                    "model": self.model,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                    "response_format": {"type": "json_object"},
                    "messages": messages,
                },
                timeout=self.timeout_seconds,
                follow_redirects=False,
            )
        except httpx.TimeoutException as exc:
            raise AIProviderError("AI_TIMEOUT", "AI request timed out", retriable=True) from exc
        except httpx.HTTPError as exc:
            raise AIProviderError("AI_PROVIDER_ERROR", "AI provider request failed", retriable=False) from exc
        latency_ms = round((time.perf_counter() - started) * 1000)
        request_id = response.headers.get("x-request-id", "")[:200]
        if response.status_code == 429:
            raise AIProviderError(
                "AI_RATE_LIMITED",
                "AI provider rate limited the request",
                retriable=True,
                http_status=429,
                request_id=request_id,
            )
        if response.status_code >= 500:
            raise AIProviderError(
                "AI_PROVIDER_5XX",
                "AI provider returned a server error",
                retriable=True,
                http_status=response.status_code,
                request_id=request_id,
            )
        if response.status_code in {401, 403}:
            raise AIProviderError(
                "AI_AUTHENTICATION_FAILED",
                "AI provider authentication failed",
                http_status=response.status_code,
                request_id=request_id,
            )
        if response.status_code >= 400:
            raise AIProviderError(
                "AI_PROVIDER_ERROR",
                f"AI provider returned HTTP {response.status_code}",
                http_status=response.status_code,
                request_id=request_id,
            )
        try:
            payload: dict[str, Any] = response.json()
        except ValueError as exc:
            raise AIProviderError(
                "AI_RESPONSE_FORMAT_ERROR",
                "AI provider response is not valid JSON",
                http_status=response.status_code,
                request_id=request_id,
            ) from exc
        return payload, latency_ms, request_id


def _optional_int(value: object) -> int | None:
    return int(value) if isinstance(value, int) and value >= 0 else None


def _parse_json_object(content: str) -> dict[str, Any]:
    stripped = content.strip()
    if stripped.startswith("```") and stripped.endswith("```"):
        lines = stripped.splitlines()
        stripped = "\n".join(lines[1:-1]).strip()
    parsed = json.loads(stripped)
    if not isinstance(parsed, dict):
        raise ValueError("connectivity response must be an object")
    return parsed
