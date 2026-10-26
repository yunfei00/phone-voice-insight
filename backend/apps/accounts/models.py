from django.conf import settings
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
