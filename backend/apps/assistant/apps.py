from django.apps import AppConfig


class AssistantConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.assistant"
    verbose_name = "AI 智能助手"

    def ready(self) -> None:
        from apps.assistant import signals  # noqa: F401
