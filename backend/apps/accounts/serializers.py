from typing import Any

from django.contrib.auth import authenticate, get_user_model, password_validation
from django.contrib.auth.models import AbstractBaseUser
from django.db import transaction
from rest_framework import serializers

from apps.accounts.models import AIProviderName, UserAIConfiguration, UserProfile, UserRole
from apps.accounts.permissions import get_user_role

User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    role = serializers.ChoiceField(choices=UserRole.choices, default=UserRole.VIEWER)
    password = serializers.CharField(write_only=True, required=False, allow_blank=False)

    class Meta:
        model = User
        fields = (
            "id",
            "username",
            "email",
            "first_name",
            "last_name",
            "role",
            "is_active",
            "last_login",
            "date_joined",
            "password",
        )
        read_only_fields = ("id", "last_login", "date_joined")

    def to_representation(self, instance: AbstractBaseUser) -> dict[str, Any]:
        data = super().to_representation(instance)
        data["role"] = get_user_role(instance)
        return data

    def validate_password(self, value: str) -> str:
        password_validation.validate_password(value, self.instance)
        return value

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        if self.instance is None and not attrs.get("password"):
            raise serializers.ValidationError({"password": "创建用户时必须设置密码。"})
        return attrs

    @transaction.atomic
    def create(self, validated_data: dict[str, Any]) -> AbstractBaseUser:
        role = validated_data.pop("role", UserRole.VIEWER)
        password = validated_data.pop("password")
        user = User.objects.create_user(password=password, **validated_data)
        UserProfile.objects.create(user=user, role=role)
        return user

    @transaction.atomic
    def update(self, instance: AbstractBaseUser, validated_data: dict[str, Any]) -> AbstractBaseUser:
        role = validated_data.pop("role", None)
        password = validated_data.pop("password", None)
        for name, value in validated_data.items():
            setattr(instance, name, value)
        if password:
            instance.set_password(password)
        instance.save()
        if role:
            UserProfile.objects.update_or_create(user=instance, defaults={"role": role})
        if password:
            instance.auth_token.delete() if hasattr(instance, "auth_token") else None
        return instance


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField(write_only=True)

    def validate(self, attrs: dict[str, str]) -> dict[str, str]:
        user = authenticate(
            request=self.context.get("request"),
            username=attrs["username"],
            password=attrs["password"],
        )
        if user is None:
            raise serializers.ValidationError("用户名或密码错误。")
        if not user.is_active:
            raise serializers.ValidationError("该账号已停用。")
        attrs["user"] = user  # type: ignore[assignment]
        return attrs


class PasswordChangeSerializer(serializers.Serializer):
    old_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True)

    def validate_old_password(self, value: str) -> str:
        if not self.context["request"].user.check_password(value):
            raise serializers.ValidationError("当前密码错误。")
        return value

    def validate_new_password(self, value: str) -> str:
        password_validation.validate_password(value, self.context["request"].user)
        return value


class UserAIConfigurationSerializer(serializers.ModelSerializer):
    api_key = serializers.CharField(write_only=True, required=False, allow_blank=False, trim_whitespace=True)
    api_key_configured = serializers.SerializerMethodField()
    api_key_masked = serializers.SerializerMethodField()
    configured = serializers.BooleanField(source="is_configured", read_only=True)

    class Meta:
        model = UserAIConfiguration
        fields = (
            "provider",
            "base_url",
            "api_key",
            "api_key_configured",
            "api_key_masked",
            "model",
            "thinking_mode",
            "timeout_seconds",
            "temperature",
            "max_output_tokens",
            "is_active",
            "configured",
            "updated_at",
        )
        read_only_fields = ("updated_at",)

    def get_api_key_configured(self, obj: UserAIConfiguration) -> bool:
        return bool(obj.api_key_ciphertext)

    def get_api_key_masked(self, obj: UserAIConfiguration) -> str:
        return f"••••••••{obj.api_key_last4}" if obj.api_key_last4 else ""

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        instance = self.instance
        provider = attrs.get("provider", getattr(instance, "provider", AIProviderName.OPENAI_COMPATIBLE))
        base_url = attrs.get("base_url", getattr(instance, "base_url", ""))
        model = attrs.get("model", getattr(instance, "model", ""))
        has_key = bool(attrs.get("api_key") or (instance and instance.api_key_ciphertext))
        if provider == AIProviderName.FAKE:
            from django.conf import settings

            if not settings.DEBUG and not settings.AI_ALLOW_FAKE_PROVIDER:
                raise serializers.ValidationError({"provider": "生产环境不允许使用测试 Provider。"})
        elif provider == AIProviderName.OLLAMA:
            if not base_url:
                raise serializers.ValidationError({"base_url": "请输入 Ollama 服务地址。"})
        elif not base_url or not has_key:
            raise serializers.ValidationError("请完整填写 API 地址和 API Key。")
        if attrs.get("is_active", getattr(instance, "is_active", True)) and not model and provider != AIProviderName.OLLAMA:
            raise serializers.ValidationError({"model": "启用配置时必须填写模型名称。"})
        return attrs

    @transaction.atomic
    def create(self, validated_data: dict[str, Any]) -> UserAIConfiguration:
        api_key = validated_data.pop("api_key", "")
        configuration = UserAIConfiguration(**validated_data)
        if api_key:
            configuration.set_api_key(api_key)
        configuration.save()
        return configuration

    @transaction.atomic
    def update(
        self,
        instance: UserAIConfiguration,
        validated_data: dict[str, Any],
    ) -> UserAIConfiguration:
        api_key = validated_data.pop("api_key", "")
        for name, value in validated_data.items():
            setattr(instance, name, value)
        if api_key:
            instance.set_api_key(api_key)
        instance.save()
        return instance
