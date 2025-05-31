"""Tests for the Article prompt field."""

from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from text_to_audio.models import Article, Feed
from text_to_audio.services.voice_configuration import VoiceConfigurationService

User = get_user_model()


class ArticlePromptTests(TestCase):
    """Test suite for Article prompt field functionality."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass123"
        )
        self.feed = Feed.objects.create(user=self.user, name="Test Feed")

    def test_article_with_prompt_creation_and_retrieval(self):
        """Test that an article with a saved prompt can be created and retrieved."""
        # Create article with prompt
        article = Article.objects.create(
            feed=self.feed,
            title="Test Article",
            text_content="This is test content.",
            prompt="This is a test prompt for TTS generation.",
        )

        # Verify prompt is saved
        self.assertEqual(article.prompt, "This is a test prompt for TTS generation.")

        # Retrieve article and verify prompt persists
        retrieved_article = Article.objects.get(pk=article.pk)
        self.assertEqual(
            retrieved_article.prompt, "This is a test prompt for TTS generation."
        )

    def test_article_prompt_default_empty_string(self):
        """Test that article prompt defaults to empty string."""
        article = Article.objects.create(
            feed=self.feed,
            title="Test Article Without Prompt",
            text_content="This is test content.",
        )

        self.assertEqual(article.prompt, "")

    @patch("text_to_audio.services.voice_configuration.VoiceParameterGenerationService")
    def test_voice_configuration_service_populates_prompt(self, mock_param_service):
        """Test that VoiceConfigurationService populates the prompt field."""
        # Mock the parameter generation service
        mock_instance = Mock()
        mock_param_service.return_value = mock_instance

        # Mock voice parameters response
        mock_voice_params = {
            "voice": "nova",
            "speed": 1.1,
            "tone": "casual",
            "affect": "friendly",
        }
        mock_instance.generate_voice_parameters.return_value = mock_voice_params

        # Mock enhanced prompt generation
        test_prompt = "Read this text in a casual, friendly tone with enthusiasm."
        mock_instance.generate_enhanced_prompt.return_value = test_prompt

        # Create article
        article = Article.objects.create(
            feed=self.feed,
            title="Test Article for Voice Config",
            text_content="This is test content for voice configuration.",
            detected_tone="casual",
        )

        # Configure voice with auto mode
        service = VoiceConfigurationService()
        service.configure_article_voice(article, force_auto=True)

        # Reload article from database
        article.refresh_from_db()

        # Verify prompt was populated
        self.assertEqual(article.prompt, test_prompt)
        # Note: The configure_article_voice method in AUTO mode saves the
        # update_fields list but doesn't actually populate voice_parameters
        # on the article. This is the expected behavior.

    def test_article_prompt_can_be_updated(self):
        """Test that article prompt can be updated."""
        article = Article.objects.create(
            feed=self.feed,
            title="Test Article",
            text_content="This is test content.",
            prompt="Initial prompt",
        )

        # Update prompt
        article.prompt = "Updated prompt for better voice generation"
        article.save()

        # Verify update persisted
        updated_article = Article.objects.get(pk=article.pk)
        self.assertEqual(
            updated_article.prompt, "Updated prompt for better voice generation"
        )

    def test_article_str_representation_unchanged(self):
        """Test that adding prompt field doesn't affect __str__ method."""
        article = Article.objects.create(
            feed=self.feed,
            title="Test Article Title",
            text_content="Content",
            prompt="Some prompt",
        )

        # Verify string representation is still the title
        self.assertEqual(str(article), "Test Article Title")
