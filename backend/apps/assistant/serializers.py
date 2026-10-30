from __future__ import annotations

from typing import Any

from django.conf import settings
from django.db import transaction
from rest_framework import serializers

from apps.accounts.models import AIProviderName
from apps.assistant.models import AssistantConversation, AssistantMessage, AssistantModelProfile
from apps.assistant.security import validate_ai_endpoint


class AssistantModelProfileSerializer(serializers.ModelSerializer):
    name = serializers.CharField(required=False, allow_blank=True, max_length=80)
    api_key = serializers.CharField(write_only=True, required=False, allow_blank=False, trim_whitespace=True)
    api_key_configured = serializers.SerializerMethodField()
    api_key_masked = serializers.SerializerMethodField()

    class Meta:
        model = AssistantModelProfile
        fields = (
            "id",
            "name",
            "provider",
            "base_url",
            "model",
            "api_key",
            "api_key_configured",
            "api_key_masked",
            "thinking_mode",
            "temperature",
            "timeout_seconds",
            "max_output_tokens",
            "is_active",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")

    def get_api_key_configured(self, obj: AssistantModelProfile) -> bool:
        return bool(obj.api_key_ciphertext)

    def get_api_key_masked(self, obj: AssistantModelProfile) -> str:
        return f"••••••••{obj.api_key_last4}" if obj.api_key_last4 else ""

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        instance = self.instance
        provider = attrs.get("provider", getattr(instance, "provider", AIProviderName.OPENAI_COMPATIBLE))
        base_url = str(attrs.get("base_url", getattr(instance, "base_url", "")))
        model = str(attrs.get("model", getattr(instance, "model", ""))).strip()
        has_key = bool(attrs.get("api_key") or (instance and instance.api_key_ciphertext))
        if provider == AIProviderName.FAKE:
            if not settings.DEBUG and not settings.AI_ALLOW_FAKE_PROVIDER:
                raise serializers.ValidationError({"provider": "生产环境不允许使用测试 Provider。"})
        else:
            if not base_url:
                raise serializers.ValidationError({"base_url": "请输入模型服务地址。"})
            attrs["base_url"] = validate_ai_endpoint(base_url, provider=str(provider))
            if provider == AIProviderName.OPENAI_COMPATIBLE and not has_key:
                raise serializers.ValidationError({"api_key": "OpenAI 兼容接口必须配置 API Key。"})
        if not model:
            raise serializers.ValidationError({"model": "请输入实际模型标识。"})
        attrs["model"] = model
        if "name" in attrs:
            attrs["name"] = str(attrs["name"]).strip() or model
        elif instance is None:
            attrs["name"] = model
        return attrs

    @transaction.atomic
    def create(self, validated_data: dict[str, Any]) -> AssistantModelProfile:
        api_key = validated_data.pop("api_key", "")
        profile = AssistantModelProfile(user=self.context["request"].user, **validated_data)
        if api_key:
            profile.set_api_key(api_key)
        profile.save()
        return profile

    @transaction.atomic
    def update(self, instance: AssistantModelProfile, validated_data: dict[str, Any]) -> AssistantModelProfile:
        api_key = validated_data.pop("api_key", "")
        for name, value in validated_data.items():
            setattr(instance, name, value)
        if api_key:
            instance.set_api_key(api_key)
        instance.save()
        return instance


class AssistantMessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = AssistantMessage
        fields = (
            "id",
            "role",
            "content",
            "request_id",
            "status",
            "model_name_snapshot",
            "provider_snapshot",
            "evidence",
            "prompt_tokens",
            "completion_tokens",
            "total_tokens",
            "latency_ms",
            "error_code",
            "error_message",
            "created_at",
        )


class AssistantConversationSerializer(serializers.ModelSerializer):
    model_profile = serializers.IntegerField(source="model_profile_id", read_only=True, allow_null=True)
    model_display = serializers.SerializerMethodField()
    message_count = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = AssistantConversation
        fields = (
            "id",
            "title",
            "model_profile",
            "use_default_model",
            "model_display",
            "status",
            "context",
            "last_message_at",
            "message_count",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "status", "last_message_at", "created_at", "updated_at")

    def get_model_display(self, obj: AssistantConversation) -> str:
        if obj.use_default_model:
            return obj.model_name_snapshot or "个人默认模型"
        if obj.model_profile:
            return obj.model_profile.name
        return obj.model_name_snapshot or "已删除的模型配置"

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        attrs["use_default_model"] = True
        attrs["model_profile"] = None
        return attrs

    def create(self, validated_data: dict[str, Any]) -> AssistantConversation:
        return AssistantConversation.objects.create(user=self.context["request"].user, **validated_data)


class AssistantChatRequestSerializer(serializers.Serializer):
    request_id = serializers.UUIDField()
    content = serializers.CharField(max_length=4000, trim_whitespace=True)
    product_id = serializers.IntegerField(required=False, allow_null=True, min_value=1)
    source_id = serializers.IntegerField(required=False, allow_null=True, min_value=1)
    start_date = serializers.DateField(required=False)
    end_date = serializers.DateField(required=False)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        if attrs.get("start_date") and attrs.get("end_date") and attrs["start_date"] > attrs["end_date"]:
            raise serializers.ValidationError("开始日期不能晚于结束日期。")
        return attrs
