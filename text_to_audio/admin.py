"""Admin configuration for the text_to_audio app.

Defines admin interfaces for Feed and Article models with appropriate
display fields, filters, and search capabilities.
"""

from django.contrib import admin

from .models import Article, Feed


@admin.register(Feed)
class FeedAdmin(admin.ModelAdmin):
    """Admin interface for the Feed model."""

    list_display = ["name", "user", "llm_provider", "created_at"]
    list_filter = ["llm_provider", "created_at"]
    search_fields = ["name", "user__username"]
    readonly_fields = ["token", "created_at"]
    fieldsets = (
        (None, {"fields": ("name", "user", "voice_mode", "llm_provider")}),
        (
            "Voice Settings",
            {"fields": ("default_voice_preset",), "classes": ("collapse",)},
        ),
        ("System", {"fields": ("token", "created_at"), "classes": ("collapse",)}),
    )


@admin.register(Article)
class ArticleAdmin(admin.ModelAdmin):
    """Admin interface for the Article model."""

    list_display = ["title", "feed", "status", "created_at", "updated_at"]
    list_filter = ["status", "created_at", "updated_at", "feed"]
    search_fields = ["title", "feed__name", "feed__user__username"]
    readonly_fields = ["created_at", "updated_at", "prompt"]
