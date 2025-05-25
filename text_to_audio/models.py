"""Models for the text_to_audio app.

This module defines the data models used for the RSS-to-TTS system, including
Feed and Article models for podcast feed generation.
"""

import uuid

from django.conf import settings
from django.db import models
from django.db.models import JSONField


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
    default_voice_preset: models.ForeignKey = models.ForeignKey(
        "UserVoicePreset",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text="Voice preset to use for new articles in this feed by default.",
    )
    created_at: models.DateTimeField = models.DateTimeField(
        auto_now_add=True, help_text="When the feed was created."
    )

    def __str__(self) -> str:
        """Return a string representation of the feed."""
        return str(self.name)


class UserVoicePreset(models.Model):
    """Model for storing user-defined voice presets."""

    user: models.ForeignKey = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="voice_presets",
        help_text="The user who owns this voice preset.",
    )
    name: models.CharField = models.CharField(
        max_length=100, help_text="Name of the voice preset."
    )
    voice_id: models.CharField = models.CharField(
        max_length=50, help_text="Voice ID for this preset."
    )
    speed: models.FloatField = models.FloatField(
        default=1.0, help_text="Speed for this preset."
    )
    prompt: models.TextField = models.TextField(
        blank=True,
        default="",
        help_text="Optional prompt describing the desired speaking style.",
    )
    sample_input: models.TextField = models.TextField(
        blank=True,
        default="",
        help_text="Optional sample text used when designing the voice.",
    )
    description: models.TextField = models.TextField(
        blank=True, help_text="Optional description of this preset."
    )
    created_at: models.DateTimeField = models.DateTimeField(
        auto_now_add=True, help_text="When the preset was created."
    )
    updated_at: models.DateTimeField = models.DateTimeField(
        auto_now=True, help_text="When the preset was last updated."
    )

    class Meta:
        unique_together = ["user", "name"]
        ordering = ["name"]

    def __str__(self) -> str:
        """Return a string representation of the preset."""
        return f"{self.name} ({self.voice_id}, {self.speed}x)"


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

    # Available voice options for TTS
    VOICE_ALLOY = "alloy"
    VOICE_ECHO = "echo"
    VOICE_FABLE = "fable"
    VOICE_ONYX = "onyx"
    VOICE_NOVA = "nova"
    VOICE_SHIMMER = "shimmer"

    VOICE_CHOICES = [
        (VOICE_ALLOY, "Alloy"),
        (VOICE_ECHO, "Echo"),
        (VOICE_FABLE, "Fable"),
        (VOICE_ONYX, "Onyx"),
        (VOICE_NOVA, "Nova"),
        (VOICE_SHIMMER, "Shimmer"),
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
    voice: models.CharField = models.CharField(
        max_length=20,
        choices=VOICE_CHOICES,
        default=VOICE_ALLOY,
        null=False,
        blank=False,
        help_text="The voice to use for text-to-speech conversion.",
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
    updated_at: models.DateTimeField = models.DateTimeField(
        auto_now=True, help_text="When the article was last updated."
    )
    celery_task_id: models.CharField = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        help_text="ID of the Celery task processing this article.",
    )
    summary: models.TextField = models.TextField(
        null=True,
        blank=True,
        help_text="AI-generated summary of the article content.",
    )
    detected_tone: models.CharField = models.CharField(
        max_length=50,
        null=True,
        blank=True,
        help_text="AI-detected tone of the article content.",
    )
    voice_id: models.CharField = models.CharField(
        max_length=50,
        null=True,
        blank=True,
        help_text="Voice ID used for text-to-speech conversion.",
    )
    speed: models.FloatField = models.FloatField(
        null=True,
        blank=True,
        help_text="Speed multiplier for text-to-speech conversion.",
    )
    voice_preset: models.ForeignKey = models.ForeignKey(
        "UserVoicePreset",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text="User-defined voice preset used for this article.",
    )
    multi_voice_data: JSONField = JSONField(
        null=True,
        blank=True,
        help_text="Stores structured data for multi-voice audio, including voice definitions and text segments.",
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

        # All articles must have audio_uuid for media access
        if not self.audio_uuid:
            # This shouldn't happen in normal operation
            raise ValueError("Article has no audio_uuid set")

        return reverse("article-media", kwargs={"audio_uuid": self.audio_uuid})


class OpenAIUsageStats(models.Model):
    """Model to track OpenAI API usage statistics."""

    user: models.ForeignKey = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=False,
        blank=False,
        help_text="The user who made the API request.",
    )
    article: models.ForeignKey = models.ForeignKey(
        "Article",  # Use string to avoid import issues if Article is defined later
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text="The article associated with this usage, if any.",
    )
    tokens_used: models.IntegerField = models.IntegerField(
        null=False, help_text="Number of tokens used in the request."
    )
    processing_time_ms: models.IntegerField = models.IntegerField(
        null=False, help_text="Processing time for the request in milliseconds."
    )
    word_count: models.IntegerField = models.IntegerField(
        null=False, help_text="Word count of the text processed."
    )
    request_timestamp: models.DateTimeField = models.DateTimeField(
        auto_now_add=True,
        null=False,
        help_text="Timestamp of when the usage was recorded.",
    )

    def __str__(self) -> str:
        """Return a string representation of the usage stat."""
        timestamp_fmt = ""  # Default empty string
        if self.request_timestamp:
            timestamp_fmt = self.request_timestamp.strftime("%Y-%m-%d %H:%M:%S")
        # Use getattr to safely access username attribute - for better type checking
        username = getattr(self.user, "username", "unknown")
        return f"Usage for {username} at {timestamp_fmt}"


class UserVoiceProfile(models.Model):
    """Model for storing user voice preferences."""

    user: models.OneToOneField = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="voice_profile",
        help_text="The user these voice preferences belong to.",
    )
    preferred_voice: models.CharField = models.CharField(
        max_length=50, null=True, blank=True, help_text="User's preferred TTS voice."
    )
    preferred_speed: models.FloatField = models.FloatField(
        default=1.0, help_text="User's preferred TTS speed multiplier."
    )
    created_at: models.DateTimeField = models.DateTimeField(
        auto_now_add=True, help_text="When the profile was created."
    )
    updated_at: models.DateTimeField = models.DateTimeField(
        auto_now=True, help_text="When the profile was last updated."
    )

    def __str__(self) -> str:
        """Return a string representation of the profile."""
        return f"Voice profile for {self.user.username}"


class VoiceMapping(models.Model):
    """Model for mapping tones to voice settings."""

    tone: models.CharField = models.CharField(
        max_length=50, unique=True, help_text="Tone category name."
    )
    voice_id: models.CharField = models.CharField(
        max_length=50, help_text="Voice ID to use for this tone."
    )
    speed: models.FloatField = models.FloatField(
        default=1.0, help_text="Speed multiplier to use for this tone."
    )
    description: models.TextField = models.TextField(
        blank=True, help_text="Description of this tone category."
    )
    is_active: models.BooleanField = models.BooleanField(
        default=True, help_text="Whether this mapping is active."
    )

    def __str__(self) -> str:
        """Return a string representation of the mapping."""
        return f"{self.tone} → {self.voice_id} ({self.speed}x)"

    class Meta:
        ordering = ["tone"]
