"""Provider factory for structured review analysis."""

from __future__ import annotations

from django.conf import settings

from ai.providers.base import AIConnectivityResponse, AIProvider, AIProviderError, AIProviderResponse
from ai.providers.fake import FakeAIProvider
from ai.providers.openai_compatible import OpenAICompatibleProvider


def get_ai_provider() -> AIProvider:
    provider = str(settings.AI_PROVIDER).strip().lower()
    if provider == "fake":
        if not settings.DEBUG and not settings.AI_ALLOW_FAKE_PROVIDER:
            raise AIProviderError("AI_FAKE_PROVIDER_FORBIDDEN", "Fake provider is disabled in production")
        return FakeAIProvider(model=settings.AI_MODEL or "fake-review-v1")
    if provider == "openai_compatible":
        missing = [
            name
            for name, value in (
                ("AI_BASE_URL", settings.AI_BASE_URL),
                ("AI_API_KEY", settings.AI_API_KEY),
                ("AI_MODEL", settings.AI_MODEL),
            )
            if not value
        ]
        if missing:
            raise AIProviderError("AI_NOT_CONFIGURED", f"Missing AI configuration: {', '.join(missing)}")
        return OpenAICompatibleProvider(
            base_url=settings.AI_BASE_URL,
            api_key=settings.AI_API_KEY,
            model=settings.AI_MODEL,
            timeout_seconds=settings.AI_TIMEOUT_SECONDS,
            temperature=settings.AI_TEMPERATURE,
            max_output_tokens=settings.AI_MAX_OUTPUT_TOKENS,
        )
    raise AIProviderError("AI_PROVIDER_UNSUPPORTED", "Configured AI provider is not supported")


__all__ = [
    "AIConnectivityResponse",
    "AIProvider",
    "AIProviderError",
    "AIProviderResponse",
    "get_ai_provider",
]
