from __future__ import annotations

import uuid

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from apps.accounts.models import AIProviderName, AIThinkingMode
from apps.common.models import TimeStampedModel


class AssistantModelProfile(TimeStampedModel):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="assistant_model_profiles",
    )
    name = models.CharField(max_length=80)
    provider = models.CharField(max_length=30, choices=AIProviderName.choices)
    base_url = models.URLField(max_length=500, blank=True)
    model = models.CharField(max_length=150)
    api_key_ciphertext = models.TextField(blank=True)
    api_key_last4 = models.CharField(max_length=4, blank=True)
    thinking_mode = models.CharField(max_length=10, choices=AIThinkingMode.choices, blank=True)
    temperature = models.DecimalField(
        max_digits=3,
        decimal_places=2,
        default=0,
        validators=(MinValueValidator(0), MaxValueValidator(2)),
    )
    timeout_seconds = models.PositiveSmallIntegerField(
        default=60,
        validators=(MinValueValidator(10), MaxValueValidator(300)),
    )
    max_output_tokens = models.PositiveIntegerField(
        default=1500,
        validators=(MinValueValidator(128), MaxValueValidator(32768)),
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("-updated_at", "-id")
        constraints = (models.UniqueConstraint(fields=("user", "name"), name="assistant_profile_user_name_unique"),)

    def set_api_key(self, api_key: str) -> None:
        from apps.accounts.crypto import encrypt_credential

        normalized = api_key.strip()
        self.api_key_ciphertext = encrypt_credential(normalized)
        self.api_key_last4 = normalized[-4:]

    def get_api_key(self) -> str:
        if not self.api_key_ciphertext:
            return ""
        from apps.accounts.crypto import decrypt_credential

        return decrypt_credential(self.api_key_ciphertext)

    def __str__(self) -> str:
        return f"{self.user_id}/{self.name}/{self.model}"


class AssistantModelSelection(models.Model):
    """One platform-wide assistant model, selected by an administrator."""

    slot = models.CharField(max_length=32, primary_key=True, default="assistant")
    profile = models.ForeignKey(AssistantModelProfile, on_delete=models.SET_NULL, null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)


class ConversationStatus(models.TextChoices):
    IDLE = "IDLE", "空闲"
    RUNNING = "RUNNING", "生成中"
    CANCELLED = "CANCELLED", "已取消"
    FAILED = "FAILED", "失败"


class AssistantConversation(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="assistant_conversations",
    )
    title = models.CharField(max_length=120, default="新对话")
    model_profile = models.ForeignKey(
        AssistantModelProfile,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="conversations",
    )
    use_default_model = models.BooleanField(default=True)
    model_name_snapshot = models.CharField(max_length=150, blank=True)
    status = models.CharField(max_length=12, choices=ConversationStatus.choices, default=ConversationStatus.IDLE)
    active_request_id = models.UUIDField(null=True, blank=True)
    context = models.JSONField(default=dict, blank=True)
    last_message_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-last_message_at", "-updated_at")
        indexes = (models.Index(fields=("user", "-last_message_at"), name="assistant_conv_user_time"),)


class MessageRole(models.TextChoices):
    USER = "USER", "用户"
    ASSISTANT = "ASSISTANT", "助手"
    SYSTEM = "SYSTEM", "系统"


class MessageStatus(models.TextChoices):
    PENDING = "PENDING", "等待中"
    RUNNING = "RUNNING", "生成中"
    COMPLETED = "COMPLETED", "已完成"
    CANCELLED = "CANCELLED", "已取消"
    FAILED = "FAILED", "失败"


class AssistantMessage(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    conversation = models.ForeignKey(
        AssistantConversation,
        on_delete=models.CASCADE,
        related_name="messages",
    )
    role = models.CharField(max_length=12, choices=MessageRole.choices)
    content = models.TextField(blank=True)
    request_id = models.UUIDField(null=True, blank=True, unique=True)
    status = models.CharField(max_length=12, choices=MessageStatus.choices, default=MessageStatus.COMPLETED)
    model_profile_id_snapshot = models.PositiveBigIntegerField(null=True, blank=True)
    model_name_snapshot = models.CharField(max_length=150, blank=True)
    provider_snapshot = models.CharField(max_length=30, blank=True)
    evidence = models.JSONField(default=list, blank=True)
    tool_trace = models.JSONField(default=list, blank=True)
    prompt_tokens = models.PositiveIntegerField(null=True, blank=True)
    completion_tokens = models.PositiveIntegerField(null=True, blank=True)
    total_tokens = models.PositiveIntegerField(null=True, blank=True)
    latency_ms = models.PositiveIntegerField(null=True, blank=True)
    error_code = models.CharField(max_length=80, blank=True)
    error_message = models.CharField(max_length=500, blank=True)

    class Meta:
        ordering = ("created_at", "id")
        indexes = (models.Index(fields=("conversation", "created_at"), name="assistant_msg_conv_time"),)
