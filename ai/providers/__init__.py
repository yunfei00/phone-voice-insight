"""Provider factory for structured review analysis."""

from __future__ import annotations

from dataclasses import dataclass

from django.conf import settings

from ai.providers.base import AIConnectivityResponse, AIProvider, AIProviderError, AIProviderResponse
from ai.providers.fake import FakeAIProvider
from ai.providers.openai_compatible import OpenAICompatibleProvider


@dataclass(frozen=True)
class AIProviderSettings:
    provider: str
    base_url: str
    api_key: str
    model: str
    thinking_mode: str = ""
    timeout_seconds: int = 60
    temperature: float = 0
    max_output_tokens: int = 1500


def _system_provider_settings() -> AIProviderSettings:
    return AIProviderSettings(
        provider=str(settings.AI_PROVIDER),
        base_url=str(settings.AI_BASE_URL),
        api_key=str(settings.AI_API_KEY),
        model=str(settings.AI_MODEL),
        thinking_mode=str(settings.AI_THINKING_MODE),
        timeout_seconds=int(settings.AI_TIMEOUT_SECONDS),
        temperature=float(settings.AI_TEMPERATURE),
        max_output_tokens=int(settings.AI_MAX_OUTPUT_TOKENS),
    )


def get_ai_provider(configuration: AIProviderSettings | None = None) -> AIProvider:
    config = configuration or _system_provider_settings()
    provider = config.provider.strip().lower()
    if provider == "fake":
        if not settings.DEBUG and not settings.AI_ALLOW_FAKE_PROVIDER:
            raise AIProviderError("AI_FAKE_PROVIDER_FORBIDDEN", "Fake provider is disabled in production")
        return FakeAIProvider(model=config.model or "fake-review-v1")
    if provider == "openai_compatible":
        thinking_mode = config.thinking_mode.strip().lower()
        if thinking_mode not in {"", "enabled", "disabled"}:
            raise AIProviderError(
                "AI_CONFIGURATION_INVALID",
                "AI_THINKING_MODE must be empty, enabled, or disabled",
            )
        missing = [
            name
            for name, value in (
                ("AI_BASE_URL", config.base_url),
                ("AI_API_KEY", config.api_key),
                ("AI_MODEL", config.model),
            )
            if not value
        ]
        if missing:
            raise AIProviderError("AI_NOT_CONFIGURED", f"Missing AI configuration: {', '.join(missing)}")
        return OpenAICompatibleProvider(
            base_url=config.base_url,
            api_key=config.api_key,
            model=config.model,
            timeout_seconds=config.timeout_seconds,
            temperature=config.temperature,
            max_output_tokens=config.max_output_tokens,
            thinking_mode=thinking_mode,
        )
    raise AIProviderError("AI_PROVIDER_UNSUPPORTED", "Configured AI provider is not supported")


__all__ = [
    "AIConnectivityResponse",
    "AIProvider",
    "AIProviderError",
    "AIProviderResponse",
    "AIProviderSettings",
    "get_ai_provider",
]
