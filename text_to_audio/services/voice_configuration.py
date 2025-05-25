"""Service for configuring TTS voice parameters."""


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

    def __init__(self, voice_mappings=None):
        """Initialize with optional voice mappings override."""
        self.voice_mappings = voice_mappings or self.DEFAULT_VOICE_MAPPINGS

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
        return [
            ("alloy", "Alloy"),
            ("ash", "Ash"),
            ("ballad", "Ballad"),
            ("coral", "Coral"),
            ("echo", "Echo"),
            ("fable", "Fable"),
            ("onyx", "Onyx"),
            ("nova", "Nova"),
            ("sage", "Sage"),
            ("shimmer", "Shimmer"),
            ("verse", "Verse"),
        ]

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
            (
                preset.id,  # type: ignore[attr-defined]
                f"{preset.name} ({preset.voice_id}, {preset.speed}x)",
            )
            for preset in presets
        ]
