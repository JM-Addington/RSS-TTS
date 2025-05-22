"""Tests for URL import functionality in the text_to_audio app."""

import os
from unittest.mock import MagicMock, patch

from django.conf import settings
from django.contrib.auth.models import User
from django.test import TestCase, override_settings

from text_to_audio.models import Article, Feed
from text_to_audio.tasks import process_article


@override_settings(CELERY_TASK_ALWAYS_EAGER=True)
class UrlImportTests(TestCase):
    """Test URL import functionality."""

    def setUp(self):
        """Set up test environment."""
        # Create test user and feed
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass"
        )
        self.feed = Feed.objects.create(user=self.user, name="Test Feed")

        # Create test directory for media
        os.makedirs(
            os.path.join(settings.MEDIA_ROOT, "articles", "1", "1"), exist_ok=True
        )

    @patch("text_to_audio.tasks.process_url_to_text")
    @patch("text_to_audio.tasks.openai.OpenAI")
    @patch("text_to_audio.tasks.AudioSegment")
    def test_process_article_with_url(
        self, mock_audio_segment, mock_openai, mock_process_url
    ):
        """Test processing an article with a URL but no text content."""
        # Setup mocks
        mock_process_url.return_value = (True, "Extracted article text from URL", None)

        mock_client = MagicMock()
        mock_openai.return_value = mock_client

        mock_response = MagicMock()
        mock_client.audio.speech.create.return_value = mock_response

        mock_empty = MagicMock()
        mock_audio_segment.empty.return_value = mock_empty

        # Create test article with URL but no text
        article = Article.objects.create(
            feed=self.feed,
            title="Test URL Article",
            source_url="https://example.com/test-article",
            text_content="",  # Empty text content
            status=Article.PROCESSING,
        )

        # Call the task
        process_article(article.pk)

        # Refresh from database
        article.refresh_from_db()

        # Verify URL processing was called
        mock_process_url.assert_called_once_with(article.source_url)

        # Verify article text was updated with extracted content
        self.assertEqual(article.text_content, "Extracted article text from URL")

        # Verify TTS was called with the extracted text
        mock_client.audio.speech.create.assert_called()

    @patch("text_to_audio.tasks.process_url_to_text")
    def test_process_article_with_url_extraction_failure(self, mock_process_url):
        """Test handling of URL extraction failure."""
        # Setup mock to return failure
        mock_process_url.return_value = (
            False,
            "",
            "Failed to extract content from URL",
        )

        # Create test article with URL but no text
        article = Article.objects.create(
            feed=self.feed,
            title="Test Failed URL Article",
            source_url="https://example.com/nonexistent-article",
            text_content="",  # Empty text content
            status=Article.PROCESSING,
        )

        # Call the task
        process_article(article.pk)

        # Refresh from database
        article.refresh_from_db()

        # Verify article is marked as failed
        self.assertEqual(article.status, Article.FAILED)
        self.assertIn("Failed to extract content from URL", article.error_message)
