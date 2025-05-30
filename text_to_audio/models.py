"""Models for the text_to_audio app.

This module defines the data models used for the RSS-to-TTS system, including
Feed and Article models for podcast feed generation.
"""

import uuid

from django.conf import settings
from django.db import models
from django.db.models import JSONField

# Available voice options for TTS (shared across models)
VOICE_ALLOY = "alloy"
VOICE_ECHO = "echo"
VOICE_FABLE = "fable"
VOICE_ASH = "ash"
VOICE_BALLAD = "ballad"
VOICE_CORAL = "coral"
VOICE_ONYX = "onyx"
VOICE_NOVA = "nova"
VOICE_SAGE = "sage"
VOICE_SHIMMER = "shimmer"
VOICE_VERSE = "verse"

VOICE_CHOICES = [
    (VOICE_ALLOY, "Alloy"),
    (VOICE_ASH, "Ash"),
    (VOICE_BALLAD, "Ballad"),
    (VOICE_CORAL, "Coral"),
    (VOICE_ECHO, "Echo"),
    (VOICE_FABLE, "Fable"),
    (VOICE_ONYX, "Onyx"),
    (VOICE_NOVA, "Nova"),
    (VOICE_SAGE, "Sage"),
    (VOICE_SHIMMER, "Shimmer"),
    (VOICE_VERSE, "Verse"),
]


class Feed(models.Model):
    """Model representing a user's collection of articles (podcast feed)."""

    # Voice mode choices
    VOICE_MODE_SINGLE_DEFAULT = "single_default"
    VOICE_MODE_SINGLE_CUSTOM = "single_custom"
    VOICE_MODE_AUTO = "auto"

    VOICE_MODE_CHOICES = [
        (VOICE_MODE_SINGLE_DEFAULT, "Single voice from defaults"),
        (VOICE_MODE_SINGLE_CUSTOM, "Single voice from custom preset"),
        (VOICE_MODE_AUTO, "Auto-generated voice"),
    ]

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
    voice_mode: models.CharField = models.CharField(
        max_length=20,
        choices=VOICE_MODE_CHOICES,
        default=VOICE_MODE_AUTO,
        help_text="Voice mode preference for this feed",
    )
    created_at: models.DateTimeField = models.DateTimeField(
        auto_now_add=True, help_text="When the feed was created."
    )

    def __str__(self) -> str:
        """Return a string representation of the feed."""
        return str(self.name)


class FollowedFeed(models.Model):
    """Represents an RSS feed a user follows and ingests into a feed."""

    user: models.ForeignKey = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="followed_feeds",
        help_text="The user who is following this feed.",
    )
    url: models.URLField = models.URLField(
        max_length=2000, help_text="The URL of the RSS feed to follow."
    )
    destination_feed: models.ForeignKey = models.ForeignKey(
        Feed,
        on_delete=models.CASCADE,
        related_name="source_feeds",
        help_text=(
            "The destination feed where articles from this followed feed will "
            "be added."
        ),
    )
    last_guid: models.CharField = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        help_text=(
            "The GUID of the last article processed from this feed. "
            "Used to avoid duplicates."
        ),
    )
    last_checked: models.DateTimeField = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When this feed was last checked for new articles.",
    )
    is_active: models.BooleanField = models.BooleanField(
        default=True,
        help_text=(
            "Whether this followed feed is currently active and should "
            "be checked for updates."
        ),
    )
    created_at: models.DateTimeField = models.DateTimeField(
        auto_now_add=True, help_text="When this followed feed was created."
    )
    updated_at: models.DateTimeField = models.DateTimeField(
        auto_now=True, help_text="When this followed feed was last updated."
    )

    def __str__(self) -> str:
        """Return a string representation of the followed feed."""
        return f"{self.url} (for {self.user.username})"  # type: ignore[attr-defined]

    class Meta:  # noqa: D106
        unique_together = ["user", "url", "destination_feed"]
        ordering = ["-created_at"]


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
        max_length=50, choices=VOICE_CHOICES, help_text="Voice ID for this preset."
    )
    speed: models.FloatField = models.FloatField(
        default=1.0, help_text="Speed for this preset."
    )
    # Enhanced voice parameters
    affect: models.CharField = models.CharField(
        max_length=50, null=True, blank=True, help_text="Emotional affect for the voice"
    )
    tone: models.CharField = models.CharField(
        max_length=100, null=True, blank=True, help_text="Tone descriptor for the voice"
    )
    pacing: models.CharField = models.CharField(
        max_length=50, null=True, blank=True, help_text="Pacing style for the voice"
    )
    pitch_variation: models.CharField = models.CharField(
        max_length=50, null=True, blank=True, help_text="Amount of pitch variation"
    )
    speaking_style: models.TextField = models.TextField(
        null=True, blank=True, help_text="Detailed description of the speaking style"
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
        """Metadata options for UserVoicePreset model."""
        unique_together = ["user", "name"]
        ordering = ["name"]

    def __str__(self) -> str:
        """Return a string representation of the preset."""
        return f"{self.name} ({self.voice_id}, {self.speed}x)"


class Article(models.Model):
    """Model representing an article that has been converted to audio.

    Voice Field Deprecation Strategy:
    ================================
    The Article model has two voice-related fields for historical reasons:
    - `voice`: CharField with predefined choices (canonical for standard voices)
    - `voice_id`: CharField for custom voice IDs (canonical for custom voices)

    IMPORTANT: Only ONE of these fields should be set at a time to maintain data consistency.
    The clean() method enforces this constraint.

    Recommended Usage:
    - Use `voice` field for standard OpenAI TTS voices (alloy, nova, etc.)
    - Use `voice_id` field for custom or future voice implementations
    - Never set both fields simultaneously

    Migration Strategy:
    - Standard voice values are normalized to the `voice` field
    - Custom voice values are normalized to the `voice_id` field
    - The validation ensures single source of truth going forward
    """

    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"

    STATUS_CHOICES = [
        (PROCESSING, "Processing"),
        (COMPLETED, "Completed"),
        (FAILED, "Failed"),
    ]

    # Use module-level voice choices as single source of truth
    VOICE_CHOICES = VOICE_CHOICES

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
        help_text=(
            "Standard OpenAI TTS voice to use for conversion. "
            "Use this field for predefined voices (alloy, nova, etc.). "
            "Do not set both 'voice' and 'voice_id' - only one should be used."
        ),
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
    detected_genre: models.CharField = models.CharField(
        max_length=50,
        null=True,
        blank=True,
        help_text="AI-detected genre of the article content.",
    )
    voice_id: models.CharField = models.CharField(
        max_length=50,
        null=True,
        blank=True,
        help_text=(
            "Custom voice ID for text-to-speech conversion. "
            "Use this field for custom or non-standard voices. "
            "Do not set both 'voice' and 'voice_id' - only one should be used. "
            "Leave empty when using standard voices."
        ),
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
        help_text=(
            "Stores structured data for multi-voice audio, including voice "
            "definitions and text segments."
        ),
    )
    voice_parameters: JSONField = JSONField(
        null=True,
        blank=True,
        help_text="Detailed voice parameters for text-to-speech conversion.",
    )

    def clean(self) -> None:
        """Validate Article model fields for consistency.

        Ensures single source of truth for voice fields:
        - Only one of 'voice' or 'voice_id' should be set at a time
        - Empty strings and whitespace-only values are treated as unset
        - Provides clear error messages for conflicts

        Raises:
            ValidationError: When both voice and voice_id are set with values
        """
        super().clean()

        # Normalize values - treat empty strings and whitespace as unset
        voice_is_set = bool(self.voice and str(self.voice).strip())
        voice_id_is_set = bool(self.voice_id and str(self.voice_id).strip())

        # Check if both fields are set
        if voice_is_set and voice_id_is_set:
            from django.core.exceptions import ValidationError
            raise ValidationError({
                'voice': f"Only one voice field should be set at a time. "
                        f"Found voice='{self.voice}' and voice_id='{self.voice_id}'. "
                        f"Please use either 'voice' for standard voices or 'voice_id' for custom voices, but not both."
            })

    def __str__(self) -> str:
        """Return a string representation of the article."""
        return str(self.title)

    def get_canonical_audio_path(self) -> str:
        """Return the canonical path for this article's audio file.

        Returns:
            The canonical path: media/audio/{user_id}/{article_id}.mp3
        """
        import os
        from django.conf import settings

        return os.path.join(
            settings.MEDIA_ROOT,
            "audio",
            str(self.feed.user.id),
            f"{self.id}.mp3"
        )

    def set_canonical_audio_path(self) -> None:
        """Set the audio_file_path to the canonical relative path."""
        import os

        relative_path = os.path.join(
            "audio",
            str(self.feed.user.id),
            f"{self.id}.mp3"
        )
        self.audio_file_path = relative_path

    def ensure_canonical_directory_exists(self) -> None:
        """Create the canonical directory structure if it doesn't exist."""
        import os
        from django.conf import settings

        # Check if MEDIA_ROOT exists first
        if not os.path.exists(settings.MEDIA_ROOT):
            raise FileNotFoundError(f"MEDIA_ROOT directory does not exist: {settings.MEDIA_ROOT}")

        user_audio_dir = os.path.join(
            settings.MEDIA_ROOT,
            "audio",
            str(self.feed.user.id)
        )
        os.makedirs(user_audio_dir, exist_ok=True)

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
        """Metadata options for VoiceMapping model."""
        ordering = ["tone"]


class VoiceGenreTemplate(models.Model):
    """Model for storing genre-specific voice templates."""

    genre: models.CharField = models.CharField(
        max_length=50, unique=True, help_text="Genre category name"
    )
    voice_id: models.CharField = models.CharField(
        max_length=50, help_text="Voice ID to use for this genre"
    )
    speed: models.FloatField = models.FloatField(
        default=1.0, help_text="Speed multiplier to use for this genre"
    )
    affect: models.CharField = models.CharField(
        max_length=50, blank=True, help_text="Emotional affect for the voice"
    )
    tone: models.CharField = models.CharField(
        max_length=100, blank=True, help_text="Tone descriptor for the voice"
    )
    pacing: models.CharField = models.CharField(
        max_length=50, blank=True, help_text="Pacing style for the voice"
    )
    pitch_variation: models.CharField = models.CharField(
        max_length=50, blank=True, help_text="Amount of pitch variation"
    )
    speaking_style: models.TextField = models.TextField(
        blank=True, help_text="Detailed description of the speaking style"
    )
    description: models.TextField = models.TextField(
        blank=True, help_text="Description of this genre category"
    )
    is_active: models.BooleanField = models.BooleanField(
        default=True, help_text="Whether this template is active"
    )
    created_at: models.DateTimeField = models.DateTimeField(
        auto_now_add=True, help_text="When the template was created"
    )
    updated_at: models.DateTimeField = models.DateTimeField(
        auto_now=True, help_text="When the template was last updated"
    )

    def __str__(self) -> str:
        """Return a string representation of the template."""
        return f"{self.genre} genre template ({self.voice_id}, {self.speed}x)"

    class Meta:
        """Metadata options for VoiceGenreTemplate model."""
        ordering = ["genre"]
