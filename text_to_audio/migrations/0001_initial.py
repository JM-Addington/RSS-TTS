"""Initial migration for text_to_audio application.

Creates the initial database schema for Feed and Article models with relationships.
"""

import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    """Initial migration creating Feed and Article models."""

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Feed",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "name",
                    models.CharField(help_text="The name of the feed.", max_length=100),
                ),
                (
                    "token",
                    models.UUIDField(
                        default=uuid.uuid4,
                        help_text="Unique token for accessing the feed.",
                        unique=True,
                    ),
                ),
                (
                    "created_at",
                    models.DateTimeField(
                        auto_now_add=True, help_text="When the feed was created."
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        help_text="The user who owns this feed.",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="feeds",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="Article",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "title",
                    models.CharField(
                        help_text="The title of the article.", max_length=255
                    ),
                ),
                (
                    "source_url",
                    models.URLField(
                        blank=True,
                        help_text="The URL of the source article.",
                        max_length=2000,
                    ),
                ),
                (
                    "text_content",
                    models.TextField(help_text="The text content of the article."),
                ),
                (
                    "audio_file_path",
                    models.CharField(
                        blank=True, help_text="Path to the audio file.", max_length=255
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("PROCESSING", "Processing"),
                            ("COMPLETED", "Completed"),
                            ("FAILED", "Failed"),
                        ],
                        default="PROCESSING",
                        help_text="The current status of the article.",
                        max_length=20,
                    ),
                ),
                (
                    "created_at",
                    models.DateTimeField(
                        auto_now_add=True, help_text="When the article was created."
                    ),
                ),
                (
                    "feed",
                    models.ForeignKey(
                        help_text="The feed this article belongs to.",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="articles",
                        to="text_to_audio.feed",
                    ),
                ),
            ],
        ),
    ]
