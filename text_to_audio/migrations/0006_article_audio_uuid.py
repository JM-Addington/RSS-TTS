"""Add audio_uuid field to Article model.

This migration adds a UUID field to the Article model to enable
unique and secure file access through the RSS feed.
"""

from django.db import migrations, models


class Migration(migrations.Migration):
    """Migration for adding audio_uuid field to Article model."""

    dependencies = [
        ("text_to_audio", "0005_alter_article_title"),
    ]

    operations = [
        migrations.AddField(
            model_name="article",
            name="audio_uuid",
            field=models.UUIDField(
                blank=True,
                help_text="Unique identifier for the audio file.",
                null=True,
                unique=True,
            ),
        ),
    ]
