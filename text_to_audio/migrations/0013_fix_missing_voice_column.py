"""Fix missing voice column in Article model.

This migration adds the voice column that was missing from the Article model.
"""

from django.db import migrations, models


class Migration(migrations.Migration):
    """Migration to fix missing voice column."""

    dependencies = [
        ("text_to_audio", "0012_fix_migration_conflicts"),
    ]

    operations = [
        # Explicitly add the voice column if it doesn't exist
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
    ]
