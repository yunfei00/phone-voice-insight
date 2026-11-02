"""OpenAI-compatible chat completions provider implemented with httpx."""

# ruff: noqa: RUF001

from __future__ import annotations

import ipaddress
import json
import time
from urllib.parse import urlsplit
from typing import Any

import httpx

from ai.providers.base import AIConnectivityResponse, AIProvider, AIProviderError, AIProviderResponse
from ai.schemas.review_analysis import ReviewAnalysisInput


def _is_local_endpoint(base_url: str) -> bool:
    """Treat loopback, RFC1918 and other non-public IP endpoints as local inference."""
    host = urlsplit(base_url).hostname
    if not host:
        return False
    if host.lower() in {"localhost", "host.docker.internal"}:
        return True
    try:
        address = ipaddress.ip_address(host)
        return not address.is_global
    except ValueError:
        return False


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
        thinking_mode: str = "",
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.temperature = temperature
        self.max_output_tokens = max_output_tokens
        self.thinking_mode = thinking_mode

    def analyze_review(
        self,
        request: ReviewAnalysisInput,
        *,
        prompt: str,
        validation_feedback: str = "",
    ) -> AIProviderResponse:
        user_payload = request.model_dump_json(exclude_none=True)
        if validation_feedback:
            user_payload = (
                f"上次输出未通过校验：{validation_feedback}\n请严格按系统提示重新输出完整 JSON。\n输入：{user_payload}"
            )
        payload, latency_ms, request_id = self._chat_completion(
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": user_payload},
            ],
            max_tokens=self.max_output_tokens,
            temperature=self.temperature,
        )
        try:
            message = payload["choices"][0]["message"]
            raw_content = message.get("content")
            content = raw_content if isinstance(raw_content, str) else ""
            if not content.strip():
                finish_reason = str(payload["choices"][0].get("finish_reason") or "unknown")
                reasoning = message.get("reasoning_content")
                detail = "reasoning_only" if reasoning else "empty_content"
                raise AIProviderError(
                    "AI_EMPTY_RESPONSE",
                    f"AI returned no JSON content ({detail}, finish_reason={finish_reason})",
                    retriable=True,
                    request_id=request_id,
                )
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
            max_tokens=256,
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
            request_payload: dict[str, Any] = {
                "model": self.model,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "response_format": {"type": "json_object"},
                "messages": messages,
            }
            if self.thinking_mode:
                request_payload["thinking"] = {"type": self.thinking_mode}
            request_bytes = len(json.dumps(request_payload, ensure_ascii=False).encode("utf-8"))
            response = httpx.post(
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                json=request_payload,
                timeout=(
                    httpx.Timeout(connect=30.0, read=None, write=60.0, pool=30.0)
                    if _is_local_endpoint(self.base_url)
                    else self.timeout_seconds
                ),
                follow_redirects=False,
                trust_env=False,
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
        if response.status_code == 413:
            raise AIProviderError(
                "AI_REQUEST_TOO_LARGE",
                f"HTTP 413: request_bytes={request_bytes}, "
                f"prompt_chars={sum(len(m.get('content', '')) for m in messages)}, "
                f"server={response.headers.get('server', 'unknown')[:60]}, "
                f"content_type={response.headers.get('content-type', 'unknown')[:60]}",
                http_status=413,
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
