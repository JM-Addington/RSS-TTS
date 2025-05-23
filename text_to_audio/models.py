"""Models for the text_to_audio app.

This module defines the data models used for the RSS-to-TTS system, including
Feed and Article models for podcast feed generation.
"""

import uuid

from django.conf import settings
from django.db import models


class Feed(models.Model):
    """Model representing a user's collection of articles (podcast feed)."""

    user: models.ForeignKey = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="feeds",
        null=False,
        blank=False,
        help_text="The user who owns this feed.",
    )
    name: models.CharField = models.CharField(
        max_length=100, null=False, blank=False, help_text="The name of the feed."
    )
    token: models.UUIDField = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        null=False,
        blank=False,
        help_text="Unique token for accessing the feed.",
    )
    created_at: models.DateTimeField = models.DateTimeField(
        auto_now_add=True, help_text="When the feed was created."
    )

    def __str__(self) -> str:
        """Return a string representation of the feed."""
        return str(self.name)


class Article(models.Model):
    """Model representing an article that has been converted to audio."""

    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"

    STATUS_CHOICES = [
        (PROCESSING, "Processing"),
        (COMPLETED, "Completed"),
        (FAILED, "Failed"),
    ]

    feed: models.ForeignKey = models.ForeignKey(
        Feed,
        on_delete=models.CASCADE,
        related_name="articles",
        null=False,
        blank=False,
        help_text="The feed this article belongs to.",
    )
    title: models.CharField = models.CharField(
        max_length=255,
        null=False,
        blank=True,
        help_text="The title of the article. Optional if URL is provided.",
    )
    source_url: models.URLField = models.URLField(
        max_length=2000, blank=True, help_text="The URL of the source article."
    )
    text_content: models.TextField = models.TextField(
        null=False, blank=True, help_text="The text content of the article."
    )
    audio_file_path: models.CharField = models.CharField(
        max_length=255, blank=True, help_text="Path to the audio file."
    )
    audio_uuid: models.UUIDField = models.UUIDField(
        unique=True,
        null=True,
        blank=True,
        help_text="Unique identifier for the audio file.",
    )
    error_message: models.TextField = models.TextField(
        blank=True, null=True, help_text="Detailed error message if processing failed."
    )
    status: models.CharField = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=PROCESSING,
        null=False,
        blank=False,
        help_text="The current status of the article.",
    )
    created_at: models.DateTimeField = models.DateTimeField(
        auto_now_add=True, help_text="When the article was created."
    )

    def __str__(self) -> str:
        """Return a string representation of the article."""
        return str(self.title)

    def get_absolute_url(self) -> str:
        """Return the URL for this article.

        Returns:
            The source URL if available, otherwise the URL to the audio file.
        """
        from django.urls import reverse

        if self.source_url:
            return str(self.source_url)
        return reverse("article-media", kwargs={"article_id": self.pk})
