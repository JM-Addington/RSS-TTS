"""Add Google Cloud TTS configuration fields to GlobalConfig."""

from django.db import migrations, models


class Migration(migrations.Migration):
    """Migration to add Google TTS configuration fields."""

    dependencies = [
        ("appconfig", "0002_globalconfig_default_tts_provider_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="globalconfig",
            name="google_tts_credentials_json",
            field=models.TextField(
                blank=True,
                help_text="Google Cloud service account credentials (JSON format)",
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="globalconfig",
            name="google_tts_default_voice_type",
            field=models.CharField(
                choices=[
                    ("gemini", "Gemini TTS (multi-speaker, prompts)"),
                    ("chirp3", "Chirp 3: HD (premium quality)"),
                    ("neural2", "Neural2 (standard quality)"),
                ],
                default="gemini",
                help_text="Default Google TTS voice type",
                max_length=50,
            ),
        ),
    ]
