from django.contrib import admin

from .models import GlobalConfig


@admin.register(GlobalConfig)
class GlobalConfigAdmin(admin.ModelAdmin):
    list_display = [
        "openai_api_key",
        "openai_tts_model",
        "openai_tts_voice",
        "firecrawl_api_key",
        "use_firecrawl_by_default",
    ]
