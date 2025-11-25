"""Add Google TTS API key field to GlobalConfig."""

from django.db import migrations, models


class Migration(migrations.Migration):
    """Migration to add Google TTS API key field (simpler alternative to JSON credentials)."""

    dependencies = [
        ("appconfig", "0003_add_google_tts_config"),
    ]

    operations = [
        migrations.AddField(
            model_name="globalconfig",
            name="google_tts_api_key",
            field=models.CharField(
                blank=True,
                help_text="Google Cloud API key (simpler alternative to service account)",
                max_length=200,
                null=True,
            ),
        ),
    ]
