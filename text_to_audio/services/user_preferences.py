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
            return {
                "voice": profile.preferred_voice,
                "speed": profile.preferred_speed
            }
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
        
        if hasattr(article, 'voice_id') and article.voice_id:
            preferences['voice'] = article.voice_id
            
        if hasattr(article, 'speed') and article.speed is not None:
            preferences['speed'] = article.speed
            
        return preferences if preferences else None
    
    def save_article_preferences(self, article, voice=None, speed=None):
        """
        Save voice preferences for a specific article.
        
        Args:
            article: Article object
            voice: Voice ID to save
            speed: Speed value to save
            
        Returns:
            Updated Article object
        """
        if voice is not None:
            article.voice_id = voice
            
        if speed is not None:
            article.speed = float(speed)
            
        article.save(update_fields=['voice_id', 'speed'])
        return article