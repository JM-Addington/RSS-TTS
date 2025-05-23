"""Django app configuration for the text_to_audio application.

Defines the app configuration including app name and database field settings.
"""

from django.apps import AppConfig


class TextToAudioConfig(AppConfig):
    """Configuration for the text_to_audio app."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "text_to_audio"
    verbose_name = "Text to Audio"
