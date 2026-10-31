from __future__ import annotations

# ruff: noqa: RUF001
import json
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Any

import httpx
from ai.providers.base import AIProviderError


@dataclass(frozen=True)
class AssistantProviderSettings:
    provider: str
    base_url: str
    api_key: str
    model: str
    thinking_mode: str
    timeout_seconds: int
    temperature: float
    max_output_tokens: int


@dataclass(frozen=True)
class AssistantUsage:
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    latency_ms: int = 0


class AssistantProviderClient:
    def __init__(self, settings: AssistantProviderSettings) -> None:
        self.settings = settings

    def plan_with_tools(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]
    ) -> tuple[str, dict[str, Any]] | None:
        if self.settings.provider == "fake":
            return None
        payload = self._post({"messages": messages, "tools": tools, "tool_choice": "auto", "stream": False})
        try:
            calls = payload["choices"][0]["message"].get("tool_calls") or []
            call = calls[0]
            return str(call["function"]["name"]), json.loads(str(call["function"]["arguments"]))
        except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError):
            return None

    def stream_summary(
        self,
        messages: list[dict[str, Any]],
        *,
        cancelled: Callable[[], bool],
    ) -> Iterator[tuple[str, AssistantUsage | None]]:
        if self.settings.provider == "fake":
            content = _fake_summary(messages)
            for offset in range(0, len(content), 24):
                if cancelled():
                    return
                yield content[offset : offset + 24], None
            yield "", AssistantUsage(total_tokens=max(len(content) // 2, 1))
            return

        started = time.perf_counter()
        request = self._request_payload({"messages": messages, "stream": True})
        try:
            with httpx.Client(trust_env=False, follow_redirects=False, timeout=self.settings.timeout_seconds) as client:
                with client.stream(
                    "POST",
                    f"{self._base_url()}/chat/completions",
                    headers=self._headers(),
                    json=request,
                ) as response:
                    self._raise_for_status(response)
                    usage: dict[str, Any] = {}
                    for line in response.iter_lines():
                        if cancelled():
                            return
                        if not line.startswith("data:"):
                            continue
                        data = line[5:].strip()
                        if data == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data)
                            usage.update(chunk.get("usage") or {})
                            text = chunk["choices"][0]["delta"].get("content") or ""
                        except (json.JSONDecodeError, KeyError, IndexError, TypeError):
                            continue
                        if text:
                            yield str(text), None
                    yield (
                        "",
                        AssistantUsage(
                            prompt_tokens=_int_or_none(usage.get("prompt_tokens")),
                            completion_tokens=_int_or_none(usage.get("completion_tokens")),
                            total_tokens=_int_or_none(usage.get("total_tokens")),
                            latency_ms=round((time.perf_counter() - started) * 1000),
                        ),
                    )
        except httpx.TimeoutException as exc:
            raise AIProviderError("ASSISTANT_TIMEOUT", "模型响应超时，请稍后重试。", retriable=True) from exc
        except httpx.HTTPError as exc:
            raise AIProviderError("ASSISTANT_PROVIDER_ERROR", "模型服务连接失败，请检查配置。") from exc

    def check_connectivity(self) -> dict[str, Any]:
        started = time.perf_counter()
        if self.settings.provider == "fake":
            return {"status": "ok", "model": self.settings.model, "latency_ms": 0}
        payload = self._post(
            {
                "messages": [{"role": "user", "content": "仅回复：连接成功"}],
                "stream": False,
                "max_tokens": 16,
            }
        )
        if not payload.get("choices"):
            raise AIProviderError("ASSISTANT_RESPONSE_INVALID", "模型返回格式无效。")
        return {
            "status": "ok",
            "model": self.settings.model,
            "latency_ms": round((time.perf_counter() - started) * 1000),
        }

    def _post(self, extra: dict[str, Any]) -> dict[str, Any]:
        try:
            response = httpx.post(
                f"{self._base_url()}/chat/completions",
                headers=self._headers(),
                json=self._request_payload(extra),
                timeout=self.settings.timeout_seconds,
                follow_redirects=False,
                trust_env=False,
            )
        except httpx.TimeoutException as exc:
            raise AIProviderError("ASSISTANT_TIMEOUT", "模型响应超时，请稍后重试。", retriable=True) from exc
        except httpx.HTTPError as exc:
            raise AIProviderError("ASSISTANT_PROVIDER_ERROR", "模型服务连接失败，请检查配置。") from exc
        self._raise_for_status(response)
        try:
            return response.json()
        except ValueError as exc:
            raise AIProviderError("ASSISTANT_RESPONSE_INVALID", "模型返回的不是合法 JSON。") from exc

    def _request_payload(self, extra: dict[str, Any]) -> dict[str, Any]:
        payload = {
            "model": self.settings.model,
            "temperature": self.settings.temperature,
            "max_tokens": self.settings.max_output_tokens,
            **extra,
        }
        if self.settings.thinking_mode:
            payload["thinking"] = {"type": self.settings.thinking_mode}
        return payload

    def _base_url(self) -> str:
        base = self.settings.base_url.rstrip("/")
        if self.settings.provider == "ollama" and not base.endswith("/v1"):
            base += "/v1"
        return base

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.settings.api_key or 'ollama'}", "Content-Type": "application/json"}

    @staticmethod
    def _raise_for_status(response: httpx.Response) -> None:
        if response.status_code == 429:
            raise AIProviderError("ASSISTANT_RATE_LIMITED", "模型服务请求过于频繁，请稍后重试。", retriable=True)
        if response.status_code in {401, 403}:
            raise AIProviderError("ASSISTANT_AUTH_FAILED", "模型服务认证失败，请检查 API Key。")
        if response.status_code >= 400:
            raise AIProviderError("ASSISTANT_PROVIDER_ERROR", f"模型服务返回 HTTP {response.status_code}。")


def _int_or_none(value: Any) -> int | None:
    return value if isinstance(value, int) and value >= 0 else None


def _fake_summary(messages: list[dict[str, Any]]) -> str:
    tool_message = next((item for item in reversed(messages) if item.get("role") == "tool"), None)
    data = json.loads(str(tool_message.get("content", "{}"))) if tool_message else {}
    meta = data.get("meta") or {}
    if "overview" in data:
        item = data["overview"]
        body = (
            f"当前范围共有 **{item.get('raw_feedback', 0)}** 条原始反馈，"
            f"其中有效反馈 **{item.get('valid_feedback', 0)}** 条，AI 已分析 **{item.get('ai_analyzed', 0)}** 条，"
            f"明确问题反馈 **{item.get('explicit_issue_feedback', 0)}** 条。"
        )
    elif "issues" in data:
        issues = data["issues"][:5]
        body = (
            "主要问题：\n"
            + "\n".join(f"- {item['product_name']} · {item['name']}：{item['feedback_count']} 条" for item in issues)
            if issues
            else "当前筛选范围暂无明确问题数据。"
        )
    elif "products" in data:
        body = "产品对比：\n" + "\n".join(
            f"- {item['product_name']}：已分析 {item['overview']['ai_analyzed']} 条，"
            f"明确问题 {item['overview']['explicit_issue_feedback']} 条"
            for item in data["products"]
        )
    elif "posts" in data:
        body = f"找到 **{len(data['posts'])}** 个匹配帖子，已附上可追溯证据和匹配依据。"
    elif "feedback" in data:
        body = f"找到 **{len(data['feedback'])}** 条匹配的有效用户反馈，已附上可追溯证据。"
    elif "issue" in data:
        issue = data["issue"]
        body = f"问题“{issue['name']}”关联 {issue['feedback_count']} 条反馈，已附上典型原始证据。"
    elif "trends" in data:
        body = f"已查询 {len(data['trends'])} 个日期的数据趋势，请结合样本量判断变化。"
    else:
        body = "当前筛选范围暂无可用数据。"
    return (
        f"### 数据事实\n\n{body}\n\n"
        f"### 数据口径\n\n时间范围：{meta.get('start_date', '未指定')} 至 {meta.get('end_date', '未指定')}；"
        f"样本量：{meta.get('sample_size', 0)}。仅使用最终有效 AI 语料。\n\n"
        "### 建议\n\n建议结合原始证据和样本覆盖率进一步核实，不将用户反馈比例等同于真实故障率。"
    )
