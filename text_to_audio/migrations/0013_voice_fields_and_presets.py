"""Add voice preset fields and fix voice column.

This migration:
1. Adds feed default_voice_preset field
2. Adds preset prompt and sample_input fields
3. Ensures voice column exists for backwards compatibility
"""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    """Migration for voice presets and voice column fix."""

    dependencies = [
        ("text_to_audio", "0012_fix_migration_conflicts"),
    ]

    operations = [
        # Add voice column for backwards compatibility
        migrations.AddField(
            model_name="article",
            name="voice",
            field=models.CharField(
                choices=[
                    ("alloy", "Alloy"),
                    ("echo", "Echo"),
                    ("fable", "Fable"),
                    ("onyx", "Onyx"),
                    ("nova", "Nova"),
                    ("shimmer", "Shimmer"),
                ],
                default="alloy",
                help_text="The voice to use for text-to-speech conversion.",
                max_length=20,
            ),
            preserve_default=True,
        ),
        # Add feed default voice preset field
        migrations.AddField(
            model_name="feed",
            name="default_voice_preset",
            field=models.ForeignKey(
                blank=True,
                help_text="Voice preset to use for new articles by default.",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                to="text_to_audio.uservoicepreset",
            ),
        ),
        # Add preset prompt field
        migrations.AddField(
            model_name="uservoicepreset",
            name="prompt",
            field=models.TextField(
                blank=True,
                default="",
                help_text="Optional prompt describing the desired speaking style.",
            ),
        ),
        # Add preset sample_input field
        migrations.AddField(
            model_name="uservoicepreset",
            name="sample_input",
            field=models.TextField(
                blank=True,
                default="",
                help_text="Optional sample text used when designing the voice.",
            ),
        ),
    ]
