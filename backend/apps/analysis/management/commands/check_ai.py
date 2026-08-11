"""Verify AI connectivity without reading reviews or exposing credentials."""

from __future__ import annotations

import json

from ai.providers import AIProviderError, get_ai_provider
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Send one minimal, review-free request to verify the configured AI provider"

    def handle(self, *_args: object, **_options: object) -> None:
        try:
            provider = get_ai_provider()
            result = provider.check_connectivity()
        except AIProviderError as exc:
            payload: dict[str, object] = {
                "connectivity": "FAIL",
                "provider": str(settings.AI_PROVIDER),
                "model": str(settings.AI_MODEL) or "NOT_CONFIGURED",
                "error_type": exc.code,
                "http_status": exc.http_status,
            }
            if exc.request_id:
                payload["provider_request_id"] = exc.request_id
            raise CommandError(json.dumps(payload, ensure_ascii=False, sort_keys=True)) from exc
        self.stdout.write(
            json.dumps(
                {
                    "connectivity": "OK",
                    "provider": result.provider,
                    "model": result.model,
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )
