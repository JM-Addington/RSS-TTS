"""Tests for auto-voice generation functionality."""

from unittest.mock import MagicMock, patch

from django.contrib.auth.models import User
from django.test import TestCase

from text_to_audio.models import Article, Feed, UserVoicePreset, VoiceGenreTemplate
from text_to_audio.services.genre_classification import GenreClassificationService
from text_to_audio.services.user_preferences import UserPreferencesService
from text_to_audio.services.voice_configuration import VoiceConfigurationService
from text_to_audio.services.voice_genre_templates import VoiceGenreTemplateService
from text_to_audio.services.voice_parameter_generation import (
    VoiceParameterGenerationService,
)


class VoiceGenreTemplateModelTest(TestCase):
    """Tests for the VoiceGenreTemplate model."""

    def setUp(self):
        """Set up test data."""
        self.template = VoiceGenreTemplate.objects.create(
            genre="news",
            voice_id="nova",
            speed=1.1,
            affect="neutral",
            tone="informative, factual",
            pacing="steady",
            pitch_variation="moderate",
            speaking_style="Clear and factual news reporting style",
            description="Template for news articles",
        )

    def test_create_template(self):
        """Test creating a voice genre template."""
        self.assertEqual(self.template.genre, "news")
        self.assertEqual(self.template.voice_id, "nova")
        self.assertEqual(self.template.speed, 1.1)
        self.assertEqual(self.template.affect, "neutral")
        self.assertEqual(self.template.tone, "informative, factual")
        self.assertEqual(self.template.pacing, "steady")
        self.assertEqual(self.template.pitch_variation, "moderate")
        self.assertEqual(
            self.template.speaking_style, "Clear and factual news reporting style"
        )
        self.assertEqual(self.template.description, "Template for news articles")
        self.assertTrue(self.template.is_active)


class VoiceGenreTemplateServiceTest(TestCase):
    """Tests for the VoiceGenreTemplateService."""

    def setUp(self):
        """Set up test data."""
        self.service = VoiceGenreTemplateService()

        # Create a template in the database
        self.db_template = VoiceGenreTemplate.objects.create(
            genre="documentary",
            voice_id="onyx",
            speed=0.95,
            affect="thoughtful",
            tone="informative, engaging",
            pacing="measured",
            pitch_variation="moderate",
            speaking_style="Nature documentary narrator style",
        )

    def test_get_template_by_genre(self):
        """Test getting a template by genre."""
        # Test default template
        news_template = self.service.get_template_by_genre("news")
        self.assertEqual(news_template["voice_id"], "nova")
        self.assertEqual(news_template["speed"], 1.1)

        # Test DB template
        documentary_template = self.service.get_template_by_genre("documentary")
        self.assertEqual(documentary_template["voice_id"], "onyx")
        self.assertEqual(documentary_template["speed"], 0.95)

    def test_get_available_genres(self):
        """Test getting available genres."""
        genres = self.service.get_available_genres()
        self.assertIsInstance(genres, list)
        self.assertTrue(len(genres) > 0)

        # Check structure
        for genre, description in genres:
            self.assertIsInstance(genre, str)
            self.assertIsInstance(description, str)


class GenreClassificationServiceTest(TestCase):
    """Tests for the GenreClassificationService."""

    def setUp(self):
        """Set up test data."""
        self.service = GenreClassificationService()
        self.article_text = (
            "Scientists have discovered a new species of butterfly in the Amazon "
            "rainforest. The discovery was made during an expedition led by Dr. "
            "Emily Carter, who specializes in tropical entomology. The butterfly, "
            "named Papilio amazonica, features vibrant blue wings with distinctive "
            "yellow patterns. This finding suggests the region's biodiversity may "
            "be even richer than previously thought."
        )

    @patch(
        "text_to_audio.services.genre_classification.GenreClassificationService.client"
    )
    def test_classify_genre(self, mock_client):
        """Test genre classification."""
        # Mock OpenAI API response
        mock_completion = MagicMock()
        mock_completion.choices = [
            MagicMock(
                message=MagicMock(
                    content=(
                        '{"genre": "news", "confidence": 0.85, '
                        '"voice_suggestions": {"affect": "neutral", '
                        '"tone": "informative", "pacing": "steady", '
                        '"pitch_variation": "moderate", "speaking_style": '
                        '"Clear and factual news reporting style"}}'
                    )
                )
            )
        ]
        mock_client.chat.completions.create.return_value = mock_completion

        # Test classification
        result = self.service.classify_genre(
            self.article_text, title="New Butterfly Species Discovered"
        )

        # Verify result
        self.assertEqual(result["genre"], "news")
        self.assertAlmostEqual(result["confidence"], 0.85)
        self.assertIn("voice_suggestions", result)
        self.assertIn("affect", result["voice_suggestions"])
        self.assertIn("tone", result["voice_suggestions"])


class VoiceParameterGenerationServiceTest(TestCase):
    """Tests for the VoiceParameterGenerationService."""

    def setUp(self):
        """Set up test data."""
        self.service = VoiceParameterGenerationService()
        self.user = User.objects.create_user(
            username="testuser", password="password123"
        )
        self.feed = Feed.objects.create(user=self.user, name="Test Feed")
        self.article = Article.objects.create(
            feed=self.feed,
            title="Test Article",
            text_content="This is a test article about science and technology.",
        )

    @patch(
        "text_to_audio.services.genre_classification."
        "GenreClassificationService.classify_genre"
    )
    @patch(
        "text_to_audio.services.content_analysis."
        "ContentAnalysisService.analyze_content"
    )
    def test_generate_voice_parameters(self, mock_analyze_content, mock_classify_genre):
        """Test voice parameter generation."""
        # Mock genre classification
        mock_classify_genre.return_value = {
            "genre": "technical",
            "confidence": 0.9,
            "voice_suggestions": {
                "affect": "focused",
                "tone": "precise, detailed",
                "pacing": "deliberate",
                "pitch_variation": "low",
                "speaking_style": "Expert explaining complex topics",
            },
        }

        # Mock content analysis
        mock_analyze_content.return_value = {
            "voices": [
                {
                    "name": "narrator",
                    "tone": "Technical expert",
                    "tts_model": "alloy",
                    "tts_speed": 0.95,
                }
            ],
            "audio_segments": [
                {
                    "text": "This is a test article about science and technology.",
                    "voice_name": "narrator",
                }
            ],
        }

        # Test parameter generation
        params = self.service.generate_voice_parameters(self.article)

        # Verify result
        self.assertIsInstance(params, dict)
        self.assertIn("voice_id", params)
        self.assertIn("speed", params)
        self.assertIn("affect", params)
        self.assertIn("tone", params)
        self.assertIn("pacing", params)

        # Check article was updated
        self.article.refresh_from_db()
        self.assertEqual(self.article.detected_genre, "technical")
        self.assertIsNotNone(self.article.voice_parameters)

    def test_generate_enhanced_prompt(self):
        """Test enhanced TTS prompt generation."""
        # Test with all parameters
        params = {
            "affect": "confident",
            "tone": "authoritative, expert",
            "pacing": "measured",
            "pitch_variation": "moderate",
            "speaking_style": (
                "Like a university professor explaining an important concept"
            ),
        }

        prompt = self.service.generate_enhanced_prompt(params)

        # Verify prompt contains all parameter types
        self.assertIn("confident affect", prompt)
        self.assertIn("authoritative, expert tone", prompt)
        self.assertIn("measured pace", prompt)
        self.assertIn("moderate pitch variation", prompt)
        self.assertIn("university professor", prompt)

        # Test with minimal parameters
        minimal_params = {
            "speaking_style": "Clear and engaging delivery",
        }

        minimal_prompt = self.service.generate_enhanced_prompt(minimal_params)
        self.assertEqual(minimal_prompt, "Clear and engaging delivery")


class FeedVoiceModeTest(TestCase):
    """Tests for feed voice mode selection."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            username="testuser", password="password123"
        )
        self.feed = Feed.objects.create(user=self.user, name="Test Feed")
        self.article = Article.objects.create(
            feed=self.feed,
            title="Test Article",
            text_content="This is a test article.",
        )
        self.preset = UserVoicePreset.objects.create(
            user=self.user,
            name="Test Preset",
            voice_id="echo",
            speed=0.9,
        )
        self.preferences_service = UserPreferencesService()
        self.voice_config_service = VoiceConfigurationService()

    def test_save_feed_voice_mode(self):
        """Test saving feed voice mode."""
        # Test single_default
        self.preferences_service.save_feed_voice_mode(
            self.feed,
            Feed.VOICE_MODE_SINGLE_DEFAULT,
        )
        self.feed.refresh_from_db()
        self.assertEqual(self.feed.voice_mode, Feed.VOICE_MODE_SINGLE_DEFAULT)

        # Test single_custom with preset
        self.preferences_service.save_feed_voice_mode(
            self.feed,
            Feed.VOICE_MODE_SINGLE_CUSTOM,
            default_voice_preset=self.preset,
        )
        self.feed.refresh_from_db()
        self.assertEqual(self.feed.voice_mode, Feed.VOICE_MODE_SINGLE_CUSTOM)
        self.assertEqual(self.feed.default_voice_preset, self.preset)

        # Test auto
        self.preferences_service.save_feed_voice_mode(
            self.feed,
            Feed.VOICE_MODE_AUTO,
        )
        self.feed.refresh_from_db()
        self.assertEqual(self.feed.voice_mode, Feed.VOICE_MODE_AUTO)

    @patch(
        "text_to_audio.services.voice_parameter_generation."
        "VoiceParameterGenerationService.generate_voice_parameters"
    )
    def test_configure_article_voice(self, mock_generate_voice_parameters):
        """Test configuring article voice based on feed mode."""  # noqa: D202

        # Mock voice parameter generation
        def fake_generate_params(article):
            article.voice_id = "alloy"
            article.speed = 1.0
            article.voice_parameters = {
                "voice_id": "alloy",
                "speed": 1.0,
                "affect": "neutral",
                "tone": "informative",
            }
            return article.voice_parameters

        mock_generate_voice_parameters.side_effect = fake_generate_params

        # Test single_default mode
        self.feed.voice_mode = Feed.VOICE_MODE_SINGLE_DEFAULT
        self.feed.save()

        self.article.detected_tone = "formal"
        self.article.save()

        self.voice_config_service.configure_article_voice(self.article)
        self.article.refresh_from_db()

        # Should use the formal tone mapping
        self.assertEqual(self.article.voice_id, "onyx")

        # Test single_custom mode
        self.feed.voice_mode = Feed.VOICE_MODE_SINGLE_CUSTOM
        self.feed.default_voice_preset = self.preset
        self.feed.save()

        # Reset article
        self.article.voice_id = None
        self.article.speed = None
        self.article.save()

        self.voice_config_service.configure_article_voice(self.article)
        self.article.refresh_from_db()

        # Should use the preset
        self.assertEqual(self.article.voice_id, "echo")
        self.assertEqual(self.article.speed, 0.9)

        # Test auto mode
        self.feed.voice_mode = Feed.VOICE_MODE_AUTO
        self.feed.save()

        # Reset article
        self.article.voice_id = None
        self.article.speed = None
        self.article.save()

        self.voice_config_service.configure_article_voice(self.article)

        # Verify generate_voice_parameters was called
        mock_generate_voice_parameters.assert_called_with(self.article)

        # Article fields should be persisted from auto generation
        self.article.refresh_from_db()
        self.assertEqual(self.article.voice_id, "alloy")
        self.assertEqual(self.article.speed, 1.0)
        self.assertEqual(
            self.article.voice_parameters,
            {
                "voice_id": "alloy",
                "speed": 1.0,
                "affect": "neutral",
                "tone": "informative",
            },
        )
