"""Admin configuration for the text_to_audio app.

Defines admin interfaces for Feed and Article models with appropriate
display fields, filters, and search capabilities.
"""

from django.contrib import admin

from .models import Article, Feed, OpenAIUsageStats


@admin.register(Feed)
class FeedAdmin(admin.ModelAdmin):
    """Admin interface for the Feed model."""

    list_display = ["name", "user", "created_at"]
    list_filter = ["created_at"]
    search_fields = ["name", "user__username"]
    readonly_fields = ["token", "created_at"]


@admin.register(Article)
class ArticleAdmin(admin.ModelAdmin):
    """Admin interface for the Article model."""

    list_display = ["title", "feed", "status", "created_at"]
    list_filter = ["status", "created_at", "feed"]
    search_fields = ["title", "feed__name", "feed__user__username"]
    readonly_fields = ["created_at", "prompt"]


@admin.register(OpenAIUsageStats)
class OpenAIUsageStatsAdmin(admin.ModelAdmin):
    """Admin interface for the OpenAIUsageStats model."""

    list_display = [
        "user",
        "operation_type",
        "model_name",
        "tokens_used",
        "estimated_cost",
        "request_timestamp",
    ]
    list_filter = ["operation_type", "model_name", "request_timestamp", "user"]
    search_fields = ["user__username", "article__title", "model_name"]
    readonly_fields = ["request_timestamp", "estimated_cost"]
    ordering = ["-request_timestamp"]

    fieldsets = (
        (
            "Request Info",
            {"fields": ("user", "article", "operation_type", "model_name")},
        ),
        (
            "Usage Metrics",
            {
                "fields": (
                    "tokens_used",
                    "input_tokens",
                    "output_tokens",
                    "word_count",
                    "processing_time_ms",
                )
            },
        ),
        ("Cost Tracking", {"fields": ("estimated_cost", "request_timestamp")}),
    )

    def get_queryset(self, request):
        """Optimize queryset with select_related."""
        return super().get_queryset(request).select_related("user", "article")
