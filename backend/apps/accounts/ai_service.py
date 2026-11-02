from decimal import Decimal

from ai.providers import AIProvider, AIProviderError, AIProviderSettings, get_ai_provider
from django.contrib.auth.models import User

from apps.accounts.crypto import CredentialDecryptionError
from apps.accounts.models import UserAIConfiguration


def get_user_ai_configuration(user: User) -> UserAIConfiguration:
    try:
        configuration = UserAIConfiguration.objects.get(user=user)
    except UserAIConfiguration.DoesNotExist as exc:
        raise AIProviderError("AI_NOT_CONFIGURED", "Personal AI configuration is missing") from exc
    if not configuration.is_configured:
        raise AIProviderError("AI_NOT_CONFIGURED", "Personal AI configuration is incomplete")
    return configuration


def provider_settings_from_model(configuration: UserAIConfiguration) -> AIProviderSettings:
    try:
        api_key = configuration.get_api_key()
    except CredentialDecryptionError as exc:
        raise AIProviderError("AI_CREDENTIAL_DECRYPTION_FAILED", "AI credential cannot be decrypted") from exc
    return AIProviderSettings(
        provider=configuration.provider,
        base_url=configuration.base_url,
        api_key=api_key,
        model=configuration.model,
        thinking_mode=configuration.thinking_mode,
        timeout_seconds=configuration.timeout_seconds,
        temperature=float(Decimal(configuration.temperature)),
        max_output_tokens=configuration.max_output_tokens,
    )


def get_user_ai_provider(user: User) -> AIProvider:
    return get_ai_provider(provider_settings_from_model(get_user_ai_configuration(user)))


def get_structured_ai_provider(user: User) -> AIProvider:
    """Use the administrator-selected analysis model; fall back to the user's configuration."""
    from apps.assistant.models import AssistantModelSelection

    selected = AssistantModelSelection.objects.select_related("profile").filter(slot="structured").first()
    if selected is None or selected.profile is None:
        return get_user_ai_provider(user)
    profile = selected.profile
    if not profile.is_active:
        raise AIProviderError("AI_NOT_CONFIGURED", "Selected structured analysis model is disabled")
    return get_ai_provider(
        AIProviderSettings(
            provider=profile.provider,
            base_url=profile.base_url,
            api_key=profile.get_api_key(),
            model=profile.model,
            thinking_mode=profile.thinking_mode,
            timeout_seconds=profile.timeout_seconds,
            temperature=float(profile.temperature),
            max_output_tokens=profile.max_output_tokens,
        )
    )
