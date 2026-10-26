from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class UserRole(models.TextChoices):
    ADMIN = "ADMIN", "管理员"
    ANALYST = "ANALYST", "分析员"
    VIEWER = "VIEWER", "只读用户"


class UserProfile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile")
    role = models.CharField(max_length=20, choices=UserRole.choices, default=UserRole.VIEWER)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "用户资料"
        verbose_name_plural = "用户资料"

    def __str__(self) -> str:
        return f"{self.user.username} ({self.get_role_display()})"


class AIProviderName(models.TextChoices):
    OPENAI_COMPATIBLE = "openai_compatible", "OpenAI 兼容接口"
    FAKE = "fake", "测试 Provider"


class AIThinkingMode(models.TextChoices):
    DEFAULT = "", "跟随模型默认"
    ENABLED = "enabled", "启用"
    DISABLED = "disabled", "禁用"


class UserAIConfiguration(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="ai_configuration",
    )
    provider = models.CharField(
        max_length=30,
        choices=AIProviderName.choices,
        default=AIProviderName.OPENAI_COMPATIBLE,
    )
    base_url = models.URLField(max_length=500, blank=True)
    api_key_ciphertext = models.TextField(blank=True)
    api_key_last4 = models.CharField(max_length=4, blank=True)
    model = models.CharField(max_length=150, blank=True)
    thinking_mode = models.CharField(max_length=10, choices=AIThinkingMode.choices, blank=True)
    timeout_seconds = models.PositiveSmallIntegerField(
        default=60,
        validators=(MinValueValidator(10), MaxValueValidator(300)),
    )
    temperature = models.DecimalField(
        max_digits=3,
        decimal_places=2,
        default=0,
        validators=(MinValueValidator(0), MaxValueValidator(2)),
    )
    max_output_tokens = models.PositiveIntegerField(
        default=1500,
        validators=(MinValueValidator(128), MaxValueValidator(32768)),
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "用户 AI 配置"
        verbose_name_plural = "用户 AI 配置"

    def __str__(self) -> str:
        return f"{self.user.username} / {self.model or 'NOT_CONFIGURED'}"

    @property
    def is_configured(self) -> bool:
        if not self.is_active or not self.model:
            return False
        if self.provider == AIProviderName.FAKE:
            return True
        return bool(self.base_url and self.api_key_ciphertext)

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
