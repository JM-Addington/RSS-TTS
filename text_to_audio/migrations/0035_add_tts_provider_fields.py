"""Add TTS provider selection fields to Feed and Article models."""

from django.db import migrations, models


class Migration(migrations.Migration):
    """Migration to add tts_provider field to Feed and Article models."""

    dependencies = [
        ("text_to_audio", "0034_add_mailgun_fields_to_feed"),
    ]

    operations = [
        migrations.AddField(
            model_name="feed",
            name="tts_provider",
            field=models.CharField(
                blank=True,
                choices=[("openai", "OpenAI"), ("google", "Google Cloud TTS")],
                help_text="TTS provider for this feed (uses global default if null)",
                max_length=50,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="article",
            name="tts_provider",
            field=models.CharField(
                blank=True,
                choices=[("openai", "OpenAI"), ("google", "Google Cloud TTS")],
                help_text="TTS provider override (inherits from feed if null)",
                max_length=50,
                null=True,
            ),
        ),
    ]
