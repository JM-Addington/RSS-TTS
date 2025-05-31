"""Service for managing user voice preferences."""


class UserPreferencesService:
    """Service for managing user voice preferences."""

    def get_user_preferences(self, user):
        """
        Get voice preferences for a user.

        Args:
            user: Django User object

        Returns:
            Dict with user preferences: {"voice": "voice_id", "speed": float}
        """
        from text_to_audio.models import UserVoiceProfile

        try:
            profile = UserVoiceProfile.objects.get(user=user)
            return {"voice": profile.preferred_voice, "speed": profile.preferred_speed}
        except (UserVoiceProfile.DoesNotExist, AttributeError):
            return None

    def save_user_preferences(self, user, voice=None, speed=None):
        """
        Save voice preferences for a user.

        Args:
            user: Django User object
            voice: Voice ID to save
            speed: Speed value to save

        Returns:
            UserVoiceProfile object
        """
        from text_to_audio.models import UserVoiceProfile

        profile, created = UserVoiceProfile.objects.get_or_create(user=user)

        if voice is not None:
            profile.preferred_voice = voice

        if speed is not None:
            profile.preferred_speed = float(speed)

        profile.save()
        return profile

    def get_article_preferences(self, article):
        """
        Get article-specific voice preferences.

        Args:
            article: Article object

        Returns:
            Dict with article preferences: {"voice": "voice_id", "speed": float}
        """
        preferences = {}

        if hasattr(article, "voice_id") and article.voice_id:
            preferences["voice"] = article.voice_id

        if hasattr(article, "speed") and article.speed is not None:
            preferences["speed"] = article.speed

        return preferences if preferences else None

    def save_article_preferences(
        self, article, voice=None, speed=None, voice_preset=None
    ):
        """
        Save voice preferences for a specific article.

        Args:
            article: Article object
            voice: Voice ID to save
            speed: Speed value to save
            voice_preset: UserVoicePreset object or ID

        Returns:
            Updated Article object
        """
        if voice_preset is not None:
            from text_to_audio.models import UserVoicePreset, VOICE_CHOICES

            standard_voices = [choice[0] for choice in VOICE_CHOICES]

            if isinstance(voice_preset, int) or isinstance(voice_preset, str):
                try:
                    preset = UserVoicePreset.objects.get(id=voice_preset)
                    article.voice_preset = preset

                    # Apply single source of truth for voice fields
                    if preset.voice_id in standard_voices:
                        # Use standard voice field for predefined voices
                        article.voice = preset.voice_id
                        article.voice_id = None
                    else:
                        # Use voice_id field for custom voices
                        article.voice_id = preset.voice_id
                        article.voice = "alloy"  # Reset to default for validation compatibility

                    article.speed = preset.speed
                except (UserVoicePreset.DoesNotExist, ValueError):
                    # If preset doesn't exist, ignore it
                    pass
            else:
                article.voice_preset = voice_preset

                # Apply single source of truth for voice fields
                if voice_preset.voice_id in standard_voices:
                    # Use standard voice field for predefined voices
                    article.voice = voice_preset.voice_id
                    article.voice_id = None
                else:
                    # Use voice_id field for custom voices
                    article.voice_id = voice_preset.voice_id
                    article.voice = "alloy"  # Reset to default for validation compatibility

                article.speed = voice_preset.speed
        else:
            if voice is not None:
                from text_to_audio.models import VOICE_CHOICES
                standard_voices = [choice[0] for choice in VOICE_CHOICES]

                # Apply single source of truth for voice fields
                if voice in standard_voices:
                    # Use standard voice field for predefined voices
                    article.voice = voice
                    article.voice_id = None
                else:
                    # Use voice_id field for custom voices
                    article.voice_id = voice
                    article.voice = "alloy"  # Reset to default for validation compatibility

            if speed is not None:
                article.speed = float(speed)

        article.save(update_fields=["voice_id", "voice", "speed", "voice_preset"])
        return article

    def get_user_presets(self, user):
        """
        Get all voice presets for a user.

        Args:
            user: Django User object

        Returns:
            QuerySet of UserVoicePreset objects
        """
        from text_to_audio.models import UserVoicePreset

        if not user or not user.is_authenticated:
            return UserVoicePreset.objects.none()

        return UserVoicePreset.objects.filter(user=user).order_by("name")

    def create_voice_preset(
        self,
        user,
        name,
        voice_id,
        speed,
        description="",
        affect=None,
        tone=None,
        pacing=None,
        pitch_variation=None,
        speaking_style=None,
    ):
        """
        Create a new voice preset for a user with enhanced parameters.

        Args:
            user: Django User object
            name: Name for the preset
            voice_id: Voice ID for the preset
            speed: Speed for the preset
            description: Optional description
            affect: Optional emotional affect
            tone: Optional tone descriptor
            pacing: Optional pacing style
            pitch_variation: Optional pitch variation
            speaking_style: Optional speaking style description

        Returns:
            Created UserVoicePreset object
        """
        from text_to_audio.models import UserVoicePreset

        preset = UserVoicePreset.objects.create(
            user=user,
            name=name,
            voice_id=voice_id,
            speed=float(speed),
            description=description,
            affect=affect,
            tone=tone,
            pacing=pacing,
            pitch_variation=pitch_variation,
            speaking_style=speaking_style,
        )

        return preset

    def update_voice_preset(
        self,
        preset_id,
        name=None,
        voice_id=None,
        speed=None,
        description=None,
        affect=None,
        tone=None,
        pacing=None,
        pitch_variation=None,
        speaking_style=None,
    ):
        """
        Update an existing voice preset with enhanced parameters.

        Args:
            preset_id: ID of the preset to update
            name: New name for the preset
            voice_id: New voice ID for the preset
            speed: New speed for the preset
            description: New description for the preset
            affect: New emotional affect
            tone: New tone descriptor
            pacing: New pacing style
            pitch_variation: New pitch variation
            speaking_style: New speaking style description

        Returns:
            Updated UserVoicePreset object or None if not found
        """
        from text_to_audio.models import UserVoicePreset

        try:
            preset = UserVoicePreset.objects.get(id=preset_id)

            if name is not None:
                preset.name = name

            if voice_id is not None:
                preset.voice_id = voice_id

            if speed is not None:
                preset.speed = float(speed)

            if description is not None:
                preset.description = description

            if affect is not None:
                preset.affect = affect

            if tone is not None:
                preset.tone = tone

            if pacing is not None:
                preset.pacing = pacing

            if pitch_variation is not None:
                preset.pitch_variation = pitch_variation

            if speaking_style is not None:
                preset.speaking_style = speaking_style

            preset.save()
            return preset

        except UserVoicePreset.DoesNotExist:
            return None

    def delete_voice_preset(self, preset_id):
        """
        Delete a voice preset.

        Args:
            preset_id: ID of the preset to delete

        Returns:
            True if deleted, False if not found
        """
        from text_to_audio.models import UserVoicePreset

        try:
            preset = UserVoicePreset.objects.get(id=preset_id)
            preset.delete()
            return True

        except UserVoicePreset.DoesNotExist:
            return False

    def get_feed_voice_mode(self, feed):
        """
        Get the voice mode for a feed.

        Args:
            feed: Feed object

        Returns:
            String voice mode ("single_default", "single_custom", or "auto")
        """
        if not hasattr(feed, "voice_mode"):
            return "single_default"  # Default if not set

        return feed.voice_mode

    def save_feed_voice_mode(self, feed, voice_mode, default_voice_preset=None):
        """
        Save voice mode preferences for a feed.

        Args:
            feed: Feed object
            voice_mode: Voice mode to save ("single_default", "single_custom", or "auto")
            default_voice_preset: Optional UserVoicePreset object or ID for
                single_custom mode

        Returns:
            Updated Feed object
        """
        from text_to_audio.models import Feed, UserVoicePreset

        # Validate voice mode
        valid_modes = [
            Feed.VOICE_MODE_SINGLE_DEFAULT,
            Feed.VOICE_MODE_SINGLE_CUSTOM,
            Feed.VOICE_MODE_AUTO,
        ]
        if voice_mode not in valid_modes:
            voice_mode = Feed.VOICE_MODE_SINGLE_DEFAULT

        feed.voice_mode = voice_mode

        # Handle voice preset if in single_custom mode
        if (
            voice_mode == Feed.VOICE_MODE_SINGLE_CUSTOM
            and default_voice_preset is not None
        ):
            if isinstance(default_voice_preset, int) or isinstance(
                default_voice_preset, str
            ):
                try:
                    preset = UserVoicePreset.objects.get(id=default_voice_preset)
                    feed.default_voice_preset = preset
                except (UserVoicePreset.DoesNotExist, ValueError):
                    # If preset doesn't exist, ignore it
                    pass
            else:
                feed.default_voice_preset = default_voice_preset

        feed.save()
        return feed
