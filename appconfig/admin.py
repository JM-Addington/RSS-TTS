from django.contrib import admin, messages
from django.utils.html import format_html

from .models import GlobalConfig


@admin.register(GlobalConfig)
class GlobalConfigAdmin(admin.ModelAdmin):
    list_display = [
        "openai_api_key",
        "openai_tts_model",
        "openai_tts_voice",
        "default_tts_provider",
        "use_firecrawl_by_default",
        "enable_chunk_tone_llm",
    ]

    fieldsets = [
        (
            "OpenAI Configuration",
            {
                "fields": [
                    "openai_api_key",
                    "openai_title_model",
                    "openai_tts_model",
                    "openai_tts_voice",
                    "openai_tts_response_format",
                    "openai_analysis_model",
                    "openai_classification_model",
                ]
            },
        ),
        (
            "Content Processing",
            {
                "fields": [
                    "use_gpt_for_url_extraction",
                    "max_analysis_words",
                ]
            },
        ),
        (
            "Firecrawl Configuration",
            {
                "fields": [
                    "firecrawl_api_key",
                    "use_firecrawl_by_default",
                ]
            },
        ),
        (
            "TTS Provider Settings",
            {
                "fields": [
                    "default_tts_provider",
                    "enable_chunk_tone_llm",
                ]
            },
        ),
        (
            "RSS/Podcast Settings",
            {
                "fields": [
                    "podcast_image_url",
                    "site_url",
                    "rss_external_hostname",
                ]
            },
        ),
    ]

    def has_module_permission(self, request):
        """Only allow super-admins to access this module."""
        return request.user.is_superuser

    def has_view_permission(self, request, obj=None):
        """Only allow super-admins to view configurations."""
        return request.user.is_superuser

    def has_add_permission(self, request):
        """Only allow super-admins to add configurations."""
        return request.user.is_superuser

    def has_change_permission(self, request, obj=None):
        """Only allow super-admins to change configurations."""
        return request.user.is_superuser

    def has_delete_permission(self, request, obj=None):
        """Only allow super-admins to delete configurations."""
        return request.user.is_superuser

    def changeform_view(self, request, object_id=None, form_url="", extra_context=None):
        """Add configuration conflict warnings to the change form."""
        extra_context = extra_context or {}

        # Check for configuration conflicts
        conflicts = GlobalConfig.get_configuration_conflicts()
        if conflicts:
            conflict_messages = []
            for conflict in conflicts:
                conflict_messages.append(
                    f"<strong>{conflict['human_name']}</strong>: Database = '{conflict['db_value']}', "
                    f"Environment = '{conflict['env_value']}' (from {conflict['env_var']})"
                )

            messages.warning(
                request,
                format_html(
                    "⚠️ <strong>Configuration Conflicts Detected!</strong><br>"
                    "The following settings have different values in the database vs environment variables. "
                    "Database values take precedence:<br><br>{}",
                    "<br>".join(conflict_messages),
                ),
                extra_tags="safe",
            )

        return super().changeform_view(request, object_id, form_url, extra_context)

    def get_readonly_fields(self, request, obj=None):
        """Add readonly fields to show configuration status."""
        readonly_fields = list(super().get_readonly_fields(request, obj))

        # Add a custom field to show migration status
        if obj:  # Only for existing objects
            readonly_fields.append("get_migration_info")

        return readonly_fields

    def get_migration_info(self, obj):
        """Display information about configuration migration status."""
        conflicts = GlobalConfig.get_configuration_conflicts()
        if conflicts:
            return format_html(
                "<span style='color: orange;'>⚠️ {} configuration conflicts detected. "
                "See warnings above for details.</span>",
                len(conflicts),
            )
        return format_html(
            "<span style='color: green;'>✅ No configuration conflicts detected.</span>"
        )

    get_migration_info.short_description = "Configuration Status"
