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
            from text_to_audio.models import UserVoicePreset

            if isinstance(voice_preset, int) or isinstance(voice_preset, str):
                try:
                    preset = UserVoicePreset.objects.get(id=voice_preset)
                    article.voice_preset = preset
                    article.voice_id = preset.voice_id
                    article.speed = preset.speed
                except (UserVoicePreset.DoesNotExist, ValueError):
                    # If preset doesn't exist, ignore it
                    pass
            else:
                article.voice_preset = voice_preset
                article.voice_id = voice_preset.voice_id
                article.speed = voice_preset.speed
        else:
            if voice is not None:
                article.voice_id = voice

            if speed is not None:
                article.speed = float(speed)

        article.save(update_fields=["voice_id", "speed", "voice_preset"])
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

    def create_voice_preset(self, user, name, voice_id, speed, description=""):
        """
        Create a new voice preset for a user.

        Args:
            user: Django User object
            name: Name for the preset
            voice_id: Voice ID for the preset
            speed: Speed for the preset
            description: Optional description

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
        )

        return preset

    def update_voice_preset(
        self, preset_id, name=None, voice_id=None, speed=None, description=None
    ):
        """
        Update an existing voice preset.

        Args:
            preset_id: ID of the preset to update
            name: New name for the preset
            voice_id: New voice ID for the preset
            speed: New speed for the preset
            description: New description for the preset

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
