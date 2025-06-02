"""Service for configuring TTS voice parameters."""

import logging

from text_to_audio.services.voice_parameter_generation import (
    VoiceParameterGenerationService,
)

logger = logging.getLogger(__name__)


def _is_mock_object(obj):
    """Check if an object is a mock (for testing)."""
    return obj is not None and hasattr(obj, "_mock_name")


class VoiceConfigurationService:
    """Service for configuring TTS voice parameters."""

    # Default voice mappings by tone
    DEFAULT_VOICE_MAPPINGS = {
        "formal": {"voice": "onyx", "speed": 1.0},
        "casual": {"voice": "nova", "speed": 1.1},
        "technical": {"voice": "alloy", "speed": 0.9},
        "storytelling": {"voice": "echo", "speed": 0.95},
        "narrative": {"voice": "fable", "speed": 1.0},
        "news": {"voice": "shimmer", "speed": 1.1},
        "conversational": {"voice": "nova", "speed": 1.05},
        # Fallback
        "neutral": {"voice": "alloy", "speed": 1.0},
    }

    def __init__(self, voice_mappings=None, openai_api_key=None):
        """Initialize with optional voice mappings override."""
        self.voice_mappings = voice_mappings or self.DEFAULT_VOICE_MAPPINGS
        self.openai_api_key = openai_api_key
        self.parameter_service = None  # Lazy initialization

    @property
    def voice_parameter_service(self):
        """Lazily initialize voice parameter generation service."""
        if self.parameter_service is None:
            self.parameter_service = VoiceParameterGenerationService(
                openai_api_key=self.openai_api_key
            )
        return self.parameter_service

    def get_voice_config(
        self,
        detected_tone,
        user_preferences=None,
        article_preferences=None,
        voice_recommendation=None,
        voice_preset=None,
    ):
        """
        Determine the final voice configuration based on tone and preferences.

        Args:
            detected_tone: The detected tone of the article
            user_preferences: Dict with user's default preferences
            article_preferences: Dict with article-specific preferences
            voice_recommendation: Dict with AI-recommended voice settings
            voice_preset: UserVoicePreset object if selected

        Returns:
            Dict with final voice config: {"voice": "voice_id", "speed": float}
        """
        # Start with the default mapping for the detected tone
        base_config = self.voice_mappings.get(
            detected_tone, self.voice_mappings["neutral"]
        ).copy()

        # Apply AI recommendation if available
        if voice_recommendation:
            if "voice" in voice_recommendation:
                base_config["voice"] = voice_recommendation["voice"]
            if "speed" in voice_recommendation:
                base_config["speed"] = voice_recommendation["speed"]

        # Apply user preferences if available
        if user_preferences:
            if user_preferences.get("voice"):
                base_config["voice"] = user_preferences["voice"]
            if user_preferences.get("speed"):
                base_config["speed"] = user_preferences["speed"]

        # Apply voice preset if specified (overrides user preferences)
        if voice_preset:
            base_config["voice"] = voice_preset.voice_id
            base_config["speed"] = voice_preset.speed

        # Apply article-specific preferences (highest priority)
        if article_preferences:
            if article_preferences.get("voice"):
                base_config["voice"] = article_preferences["voice"]
            if article_preferences.get("speed"):
                base_config["speed"] = article_preferences["speed"]

        # Validate and constrain values
        speed = base_config.get("speed", 1.0)
        if isinstance(speed, (int, float)):
            base_config["speed"] = max(0.75, min(1.5, float(speed)))

        return base_config

    def get_available_voices(self):
        """
        Get list of available voices with labels.

        Returns:
            List of tuples: [(voice_id, display_name), ...]
        """
        from text_to_audio.models import VOICE_CHOICES

        return VOICE_CHOICES

    def get_available_speeds(self):
        """
        Get list of available speed presets with labels.

        Returns:
            List of tuples: [(speed_value, display_name), ...]
        """
        return [
            (0.75, "Very Slow (0.75x)"),
            (0.9, "Slow (0.9x)"),
            (1.0, "Normal (1.0x)"),
            (1.1, "Slightly Fast (1.1x)"),
            (1.25, "Fast (1.25x)"),
            (1.5, "Very Fast (1.5x)"),
        ]

    def get_user_presets(self, user):
        """
        Get a list of user's custom voice presets.

        Args:
            user: Django User object

        Returns:
            List of tuples: [(preset_id, preset_name), ...]
        """
        from text_to_audio.models import UserVoicePreset

        if not user or not user.is_authenticated:
            return []

        presets = UserVoicePreset.objects.filter(user=user).order_by("name")
        return [
            (preset.pk, f"{preset.name} ({preset.voice_id}, {preset.speed}x)")
            for preset in presets
        ]

    def configure_article_voice(self, article, force_auto=False):
        """
        Configure the voice settings for an article based on feed preferences.

        This method handles the different voice mode strategies:
        - single_default: Use tone-based voice mapping
        - single_custom: Use feed's default voice preset
        - auto: Generate AI-driven voice parameters

        Args:
            article: Article object to configure
            force_auto: Whether to force auto-generated voice regardless of feed setting

        Returns:
            Updated Article object with voice configuration applied
        """
        from text_to_audio.models import Feed
        from text_to_audio.services.user_preferences import UserPreferencesService

        preferences_service = UserPreferencesService()
        feed = article.feed

        # Determine voice mode to use
        voice_mode = preferences_service.get_feed_voice_mode(feed)

        # If force_auto is True, always use auto voice generation
        if force_auto:
            voice_mode = Feed.VOICE_MODE_AUTO

        # Apply the appropriate voice configuration strategy
        if voice_mode == Feed.VOICE_MODE_SINGLE_CUSTOM and feed.default_voice_preset:
            # Apply feed's default voice preset
            preferences_service.save_article_preferences(
                article=article, voice_preset=feed.default_voice_preset
            )

        elif voice_mode == Feed.VOICE_MODE_AUTO:
            # Generate AI-driven voice parameters
            try:
                voice_parameters = (
                    self.voice_parameter_service.generate_voice_parameters(article)
                )
                # Validate that we got actual data, not a mock
                if _is_mock_object(voice_parameters):
                    voice_parameters = None
            except Exception as e:
                logger.error(f"Voice parameter generation failed: {e}")
                voice_parameters = None

            # Generate enhanced TTS prompt if needed
            update_fields = ["voice_id", "speed", "voice_parameters", "detected_genre"]

            if voice_parameters:
                enhanced_prompt = self.voice_parameter_service.generate_enhanced_prompt(
                    voice_parameters
                )
                if enhanced_prompt:
                    article.prompt = enhanced_prompt
                    update_fields.append("prompt")

            # Persist generated parameters on the article
            article.save(update_fields=update_fields)

        else:
            # Use default tone-based voice mapping
            # First detect the tone if not already done
            if not article.detected_tone:
                # Use a simple fallback if no tone detected
                article.detected_tone = "neutral"
                article.save(update_fields=["detected_tone"])

            # Get voice config based on tone
            voice_config = self.get_voice_config(article.detected_tone)

            # Apply the config
            preferences_service.save_article_preferences(
                article=article,
                voice=voice_config["voice"],
                speed=voice_config["speed"],
            )

        return article

    def get_available_voice_modes(self):
        """
        Get list of available voice modes with labels.

        Returns:
            List of tuples: [(mode_value, display_name), ...]
        """
        from text_to_audio.models import Feed

        return [
            (Feed.VOICE_MODE_SINGLE_DEFAULT, "Single voice (default)"),
            (Feed.VOICE_MODE_SINGLE_CUSTOM, "Single voice (custom preset)"),
            (Feed.VOICE_MODE_AUTO, "Auto-generated voice"),
        ]

    def voice_for_character(self, char_name: str, payload) -> str:
        """
        Get voice for a character from ChunkTonePayload.

        Args:
            char_name: Character name to find voice for
            payload: ChunkTonePayload or similar object with chunks

        Returns:
            Voice ID string, defaults to "alloy" if not found
        """
        if hasattr(payload, "chunks"):
            for chunk in payload.chunks:
                if (
                    hasattr(chunk, "character_name")
                    and chunk.character_name == char_name
                    and hasattr(chunk, "voice")
                    and hasattr(chunk.voice, "voice")
                ):
                    return chunk.voice.voice

        # Fallback to default voice
        return "alloy"
