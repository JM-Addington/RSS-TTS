"""Test for OpenAI usage logging integration across services."""

from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from text_to_audio.models import Feed, Article, OpenAIUsageStats
from text_to_audio.services.usage_logging import UsageLogger
from text_to_audio.services.chunk_tone_service import ChunkToneService
from text_to_audio.services.genre_classification import GenreClassificationService
from text_to_audio.services.content_analysis import ContentAnalysisService

User = get_user_model()


class UsageLoggingIntegrationTests(TestCase):
    """Test OpenAI usage logging across all services."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass123"
        )
        self.feed = Feed.objects.create(user=self.user, name="Test Feed")
        self.article = Article.objects.create(
            feed=self.feed,
            title="Test Article",
            text_content="This is a test article with enough content to analyze.",
        )

    def test_usage_logger_logs_llm_usage_correctly(self):
        """Test that UsageLogger correctly logs LLM usage to OpenAIUsageStats."""
        usage_logger = UsageLogger(self.user, self.article, "Test")

        # Check initial state
        self.assertEqual(OpenAIUsageStats.objects.count(), 0)

        # Log usage
        usage_logger.log_llm_usage(
            operation="Test Operation",
            tokens_used=100,
            processing_time_ms=1500,
            word_count=20
        )

        # Verify usage was logged
        self.assertEqual(OpenAIUsageStats.objects.count(), 1)
        stats = OpenAIUsageStats.objects.first()
        self.assertEqual(stats.user, self.user)
        self.assertEqual(stats.article, self.article)
        self.assertEqual(stats.tokens_used, 100)
        self.assertEqual(stats.processing_time_ms, 1500)
        self.assertEqual(stats.word_count, 20)

    @patch('text_to_audio.services.chunk_tone_service.openai.OpenAI')
    def test_chunk_tone_service_logs_usage(self, mock_openai_class):
        """Test that ChunkToneService logs usage when usage_logger is provided."""
        # Set up mock response
        mock_client = Mock()
        mock_openai_class.return_value = mock_client

        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message.content = """{
            "chunks": [
                {
                    "text": "Test chunk",
                    "voice": {"voice": "alloy"},
                    "instructions": "Test instructions",
                    "character_name": "narrator"
                }
            ]
        }"""
        mock_response.usage = Mock()
        mock_response.usage.total_tokens = 50
        mock_response.usage.prompt_tokens = 30
        mock_response.usage.completion_tokens = 20
        mock_response.id = "test-id"
        mock_response.model = "gpt-4o-mini"
        mock_response.object = "chat.completion"
        mock_response.created = 1234567890

        mock_client.chat.completions.create.return_value = mock_response

        # Create usage logger and service
        usage_logger = UsageLogger(self.user, self.article, "ChunkTone")
        service = ChunkToneService(usage_logger=usage_logger)

        # Check initial state
        self.assertEqual(OpenAIUsageStats.objects.count(), 0)

        # Call service
        result = service.get_payload("Test text content", "Test Title", 4000)

        # Verify API was called
        mock_client.chat.completions.create.assert_called_once()

        # Verify usage was logged
        self.assertEqual(OpenAIUsageStats.objects.count(), 1)
        stats = OpenAIUsageStats.objects.first()
        self.assertEqual(stats.user, self.user)
        self.assertEqual(stats.article, self.article)
        self.assertEqual(stats.tokens_used, 50)

    def test_genre_classification_service_logs_usage(self):
        """Test that GenreClassificationService logs usage when usage_logger is provided."""
        # Set up mock response
        mock_client = Mock()

        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message.content = """{
            "genre": "news",
            "confidence": 0.85,
            "voice_suggestions": {
                "affect": "neutral",
                "tone": "informative"
            }
        }"""
        mock_response.usage = Mock()
        mock_response.usage.total_tokens = 25

        mock_client.chat.completions.create.return_value = mock_response

        # Create usage logger and service
        usage_logger = UsageLogger(self.user, self.article, "Genre")
        service = GenreClassificationService(usage_logger=usage_logger)

        # Mock the client property
        service._client = mock_client

        # Check initial state
        self.assertEqual(OpenAIUsageStats.objects.count(), 0)

        # Call service
        result = service.classify_genre("Test article content", "Test Title")

        # Verify API was called
        mock_client.chat.completions.create.assert_called_once()

        # Verify usage was logged
        self.assertEqual(OpenAIUsageStats.objects.count(), 1)
        stats = OpenAIUsageStats.objects.first()
        self.assertEqual(stats.user, self.user)
        self.assertEqual(stats.article, self.article)
        self.assertEqual(stats.tokens_used, 25)

    def test_content_analysis_service_logs_usage(self):
        """Test that ContentAnalysisService logs usage when usage_logger is provided."""
        # Set up mock response
        mock_client = Mock()

        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message.content = """{
            "voices": [
                {
                    "name": "narrator",
                    "tone": "neutral",
                    "tts_model": "alloy",
                    "tts_speed": 1.0
                }
            ],
            "audio_segments": [
                {
                    "text": "Test segment",
                    "voice_name": "narrator"
                }
            ]
        }"""
        mock_response.usage = Mock()
        mock_response.usage.total_tokens = 75
        mock_response.usage.prompt_tokens = 50
        mock_response.usage.completion_tokens = 25
        mock_response.id = "test-id"
        mock_response.model = "gpt-4o-mini"
        mock_response.object = "chat.completion"
        mock_response.created = 1234567890

        mock_client.chat.completions.create.return_value = mock_response

        # Create usage logger and service
        usage_logger = UsageLogger(self.user, self.article, "Content")
        service = ContentAnalysisService(usage_logger=usage_logger)

        # Mock the client property
        service._client = mock_client

        # Check initial state
        self.assertEqual(OpenAIUsageStats.objects.count(), 0)

        # Call service
        result = service.analyze_content("Test article content", "Test Title")

        # Verify API was called
        mock_client.chat.completions.create.assert_called_once()

        # Verify usage was logged
        self.assertEqual(OpenAIUsageStats.objects.count(), 1)
        stats = OpenAIUsageStats.objects.first()
        self.assertEqual(stats.user, self.user)
        self.assertEqual(stats.article, self.article)
        self.assertEqual(stats.tokens_used, 75)

    def test_services_work_without_usage_logger(self):
        """Test that services still work when no usage_logger is provided."""
        with patch('text_to_audio.services.chunk_tone_service.openai.OpenAI') as mock_openai:
            mock_client = Mock()
            mock_openai.return_value = mock_client

            mock_response = Mock()
            mock_response.choices = [Mock()]
            mock_response.choices[0].message.content = """{
                "chunks": [
                    {
                        "text": "Test chunk",
                        "voice": {"voice": "alloy"},
                        "instructions": "Test instructions",
                        "character_name": "narrator"
                    }
                ]
            }"""
            mock_response.usage = Mock()
            mock_response.usage.total_tokens = 50
            mock_response.id = "test-id"
            mock_response.model = "gpt-4o-mini"
            mock_response.object = "chat.completion"
            mock_response.created = 1234567890

            mock_client.chat.completions.create.return_value = mock_response

            # Create service without usage logger
            service = ChunkToneService()

            # Should not crash
            result = service.get_payload("Test text content", "Test Title", 4000)

            # No usage should be logged
            self.assertEqual(OpenAIUsageStats.objects.count(), 0)

    def test_multiple_services_log_separate_usage(self):
        """Test that different services log separate usage entries."""
        with patch('text_to_audio.services.chunk_tone_service.openai.OpenAI') as mock_chunk_openai:

            # Set up ChunkToneService mock
            mock_chunk_client = Mock()
            mock_chunk_openai.return_value = mock_chunk_client
            mock_chunk_response = Mock()
            mock_chunk_response.choices = [Mock()]
            mock_chunk_response.choices[0].message.content = """{
                "chunks": [{"text": "Test", "voice": {"voice": "alloy"}, "instructions": "Test", "character_name": "narrator"}]
            }"""
            mock_chunk_response.usage = Mock()
            mock_chunk_response.usage.total_tokens = 50
            mock_chunk_response.id = "test-id-1"
            mock_chunk_response.model = "gpt-4o-mini"
            mock_chunk_response.object = "chat.completion"
            mock_chunk_response.created = 1234567890
            mock_chunk_client.chat.completions.create.return_value = mock_chunk_response

            # Set up GenreClassificationService mock
            mock_genre_client = Mock()
            mock_genre_response = Mock()
            mock_genre_response.choices = [Mock()]
            mock_genre_response.choices[0].message.content = """{
                "genre": "news", "confidence": 0.85, "voice_suggestions": {}
            }"""
            mock_genre_response.usage = Mock()
            mock_genre_response.usage.total_tokens = 25
            mock_genre_client.chat.completions.create.return_value = mock_genre_response

            # Create different usage loggers for each service
            chunk_logger = UsageLogger(self.user, self.article, "ChunkTone")
            genre_logger = UsageLogger(self.user, self.article, "Genre")

            chunk_service = ChunkToneService(usage_logger=chunk_logger)
            genre_service = GenreClassificationService(usage_logger=genre_logger)

            # Mock the genre service client directly
            genre_service._client = mock_genre_client

            # Call both services
            chunk_service.get_payload("Test text", "Test Title", 4000)
            genre_service.classify_genre("Test content", "Test Title")

            # Should have logged 2 separate usage entries
            self.assertEqual(OpenAIUsageStats.objects.count(), 2)

            # Verify different token counts
            token_counts = list(OpenAIUsageStats.objects.values_list('tokens_used', flat=True))
            self.assertIn(50, token_counts)  # ChunkTone
            self.assertIn(25, token_counts)  # Genre
