from django.contrib import admin

from apps.assistant.models import AssistantConversation, AssistantMessage, AssistantModelProfile

admin.site.register(AssistantModelProfile)
admin.site.register(AssistantConversation)
admin.site.register(AssistantMessage)
