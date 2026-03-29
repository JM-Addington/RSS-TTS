"""Tests to verify voice field single source of truth fixes work correctly."""

from django.contrib.auth import get_user_model
from django.test import TestCase

from text_to_audio.models import (VOICE_ALLOY, VOICE_NOVA, Article, Feed,
                                  UserVoicePreset)
from text_to_audio.services.user_preferences import UserPreferencesService
from text_to_audio.services.voice_parameter_generation import \
    VoiceParameterGenerationService

User = get_user_model()


class VoiceSingleSourceFixTests(TestCase):
    """Test that services correctly implement single source of truth for voice fields."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass123"
        )
        self.feed = Feed.objects.create(user=self.user, name="Test Feed")
        self.article = Article.objects.create(
            feed=self.feed,
            title="Test Article",
            text_content="Test content for voice analysis",
            voice=VOICE_ALLOY,  # Start with a standard voice
        )

    def test_user_preferences_service_handles_standard_voice(self):
        """Test that UserPreferencesService correctly handles standard voices."""
        service = UserPreferencesService()

        # Save a standard voice
        service.save_article_preferences(article=self.article, voice=VOICE_NOVA)

        # Reload from database
        self.article.refresh_from_db()

        # Should use voice field for standard voice
        self.assertEqual(self.article.voice, VOICE_NOVA)
        self.assertIsNone(self.article.voice_id)

        # Article should pass validation
        self.article.clean()  # Should not raise ValidationError

    def test_user_preferences_service_handles_custom_voice(self):
        """Test that UserPreferencesService correctly handles custom voices."""
        service = UserPreferencesService()

        # Save a custom voice
        custom_voice = "custom_voice_123"
        service.save_article_preferences(article=self.article, voice=custom_voice)

        # Reload from database
        self.article.refresh_from_db()

        # Should use voice_id field for custom voice
        self.assertEqual(self.article.voice_id, custom_voice)
        self.assertEqual(self.article.voice, VOICE_ALLOY)  # Reset to default

        # Article should pass validation
        self.article.clean()  # Should not raise ValidationError

    def test_user_preferences_service_handles_voice_preset_standard(self):
        """Test that UserPreferencesService correctly handles presets with standard voices."""
        # Create a preset with standard voice
        preset = UserVoicePreset.objects.create(
            user=self.user, name="Standard Preset", voice_id=VOICE_NOVA, speed=1.2
        )

        service = UserPreferencesService()
        service.save_article_preferences(article=self.article, voice_preset=preset)

        # Reload from database
        self.article.refresh_from_db()

        # Should use voice field for standard voice from preset
        self.assertEqual(self.article.voice, VOICE_NOVA)
        self.assertIsNone(self.article.voice_id)
        self.assertEqual(self.article.speed, 1.2)

        # Article should pass validation
        self.article.clean()  # Should not raise ValidationError

    def test_user_preferences_service_handles_voice_preset_custom(self):
        """Test that UserPreferencesService correctly handles presets with custom voices."""
        # Create a preset with custom voice
        custom_voice = "custom_preset_voice"
        preset = UserVoicePreset.objects.create(
            user=self.user, name="Custom Preset", voice_id=custom_voice, speed=0.9
        )

        service = UserPreferencesService()
        service.save_article_preferences(article=self.article, voice_preset=preset)

        # Reload from database
        self.article.refresh_from_db()

        # Should use voice_id field for custom voice from preset
        self.assertEqual(self.article.voice_id, custom_voice)
        self.assertEqual(self.article.voice, VOICE_ALLOY)  # Reset to default
        self.assertEqual(self.article.speed, 0.9)

        # Article should pass validation
        self.article.clean()  # Should not raise ValidationError

    def test_voice_parameter_generation_service_standard_voice(self):
        """Test that VoiceParameterGenerationService handles standard voices correctly."""
        service = VoiceParameterGenerationService()

        # Mock the services to return a standard voice
        service.genre_service.classify_genre = lambda *args, **kwargs: {
            "genre": "news",
            "voice_suggestions": {"voice_id": VOICE_NOVA},
        }
        service.template_service.get_template_by_genre = lambda genre: {
            "voice_id": VOICE_NOVA,
            "speed": 1.1,
        }
        service.content_service.analyze_content = lambda *args, **kwargs: None

        # Generate parameters
        service.generate_voice_parameters(self.article)

        # Reload from database
        self.article.refresh_from_db()

        # Should use voice field for standard voice
        self.assertEqual(self.article.voice, VOICE_NOVA)
        self.assertIsNone(self.article.voice_id)

        # Article should pass validation
        self.article.clean()  # Should not raise ValidationError

    def test_voice_parameter_generation_service_custom_voice(self):
        """Test that VoiceParameterGenerationService handles custom voices correctly."""
        service = VoiceParameterGenerationService()

        custom_voice = "custom_ai_voice"

        # Mock the services to return a custom voice
        service.genre_service.classify_genre = lambda *args, **kwargs: {
            "genre": "fiction",
            "voice_suggestions": {"voice_id": custom_voice},
        }
        service.template_service.get_template_by_genre = lambda genre: {
            "voice_id": custom_voice,
            "speed": 1.3,
        }
        service.content_service.analyze_content = lambda *args, **kwargs: None

        # Generate parameters
        service.generate_voice_parameters(self.article)

        # Reload from database
        self.article.refresh_from_db()

        # Should use voice_id field for custom voice
        self.assertEqual(self.article.voice_id, custom_voice)
        self.assertEqual(self.article.voice, VOICE_ALLOY)  # Reset to default

        # Article should pass validation
        self.article.clean()  # Should not raise ValidationError

    def test_article_clean_passes_after_service_operations(self):
        """Test that Article.clean() passes after various service operations."""
        service = UserPreferencesService()

        # Test multiple operations that previously would have caused conflicts

        # 1. Save standard voice
        service.save_article_preferences(article=self.article, voice=VOICE_NOVA)
        self.article.refresh_from_db()
        self.article.clean()  # Should pass

        # 2. Save custom voice
        service.save_article_preferences(
            article=self.article, voice="custom_voice_test"
        )
        self.article.refresh_from_db()
        self.article.clean()  # Should pass

        # 3. Apply preset with standard voice
        preset = UserVoicePreset.objects.create(
            user=self.user, name="Test Preset", voice_id=VOICE_NOVA, speed=1.0
        )
        service.save_article_preferences(article=self.article, voice_preset=preset)
        self.article.refresh_from_db()
        self.article.clean()  # Should pass
