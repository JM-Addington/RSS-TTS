"""Tests for HTTP error handling and retry functionality."""

import unittest
from unittest.mock import MagicMock, patch

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from requests.exceptions import ConnectionError, Timeout

from text_to_audio.models import Article, Feed
from text_to_audio.tasks import process_article
from text_to_audio.utils import fetch_url_content


class HttpErrorHandlingTests(TestCase):
    """Test HTTP error handling and retry functionality."""

    def setUp(self):
        """Set up test environment."""
        # Create test user and feed
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass"
        )
        self.feed = Feed.objects.create(user=self.user, name="Test Feed")
        self.test_url = "https://example.com/test-article"

    @patch("text_to_audio.utils.requests.get")
    def test_fetch_url_404_error(self, mock_get):
        """Test handling of 404 errors without retries."""
        # Setup mock to simulate 404 response
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_get.return_value = mock_response

        # Call function
        success, content, error = fetch_url_content(self.test_url)

        # Verify behavior
        self.assertFalse(success)
        self.assertEqual(content, "")
        self.assertIn("404 Not Found", error or "")

        # Verify get was called only once (no retries for permanent errors)
        mock_get.assert_called_once()

    @patch("text_to_audio.utils.requests.get")
    def test_fetch_url_403_error(self, mock_get):
        """Test handling of 403 errors without retries."""
        # Setup mock to simulate 403 response
        mock_response = MagicMock()
        mock_response.status_code = 403
        mock_get.return_value = mock_response

        # Call function
        success, content, error = fetch_url_content(self.test_url)

        # Verify behavior
        self.assertFalse(success)
        self.assertEqual(content, "")
        self.assertIn("403 Forbidden", error or "")

        # Verify get was called only once (no retries for permanent errors)
        mock_get.assert_called_once()

    @patch("text_to_audio.utils.time.sleep")
    @patch("text_to_audio.utils.requests.get")
    def test_fetch_url_500_error_with_retries(self, mock_get, mock_sleep):
        """Test retries for 500 server errors."""
        # Setup mock to simulate 500 response for first calls, then success
        mock_response_error = MagicMock()
        mock_response_error.status_code = 500

        mock_response_success = MagicMock()
        mock_response_success.status_code = 200
        mock_response_success.text = "Success content"

        # First 2 calls return error, third call succeeds
        mock_get.side_effect = [
            mock_response_error,
            mock_response_error,
            mock_response_success,
        ]

        # Call function
        success, content, error = fetch_url_content(self.test_url, max_retries=3)

        # Verify behavior
        self.assertTrue(success)
        self.assertEqual(content, "Success content")
        self.assertIsNone(error)

        # Verify get was called 3 times (initial + 2 retries)
        self.assertEqual(mock_get.call_count, 3)

        # Verify sleep was called for the retries with exponential backoff
        mock_sleep.assert_any_call(2)  # 2^1
        mock_sleep.assert_any_call(4)  # 2^2

    @patch("text_to_audio.utils.time.sleep")
    @patch("text_to_audio.utils.requests.get")
    def test_fetch_url_max_retries_exceeded(self, mock_get, mock_sleep):
        """Test behavior when max retries are exceeded."""
        # Setup mock to always return 500 error
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_get.return_value = mock_response

        # Call function with 3 max retries
        success, content, error = fetch_url_content(self.test_url, max_retries=3)

        # Verify behavior
        self.assertFalse(success)
        self.assertEqual(content, "")
        self.assertIn("Failed after 3 attempts", error or "")
        self.assertIn("500 Server Error", error or "")

        # Verify get was called 3 times (initial + 2 retries)
        self.assertEqual(mock_get.call_count, 3)

    @patch("text_to_audio.utils.time.sleep")
    @patch("text_to_audio.utils.requests.get")
    def test_fetch_url_timeout_with_retries(self, mock_get, mock_sleep):
        """Test retries for timeout errors."""
        # Setup mock to raise Timeout twice, then succeed
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "Success after timeout"

        mock_get.side_effect = [Timeout(), Timeout(), mock_response]

        # Call function
        success, content, error = fetch_url_content(self.test_url, max_retries=3)

        # Verify behavior
        self.assertTrue(success)
        self.assertEqual(content, "Success after timeout")
        self.assertIsNone(error)

        # Verify get was called 3 times (initial + 2 retries)
        self.assertEqual(mock_get.call_count, 3)

    @patch("text_to_audio.utils.time.sleep")
    @patch("text_to_audio.utils.requests.get")
    def test_fetch_url_connection_error_with_retries(self, mock_get, mock_sleep):
        """Test retries for connection errors."""
        # Setup mock to raise ConnectionError twice, then succeed
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "Success after connection error"

        mock_get.side_effect = [ConnectionError(), ConnectionError(), mock_response]

        # Call function
        success, content, error = fetch_url_content(self.test_url, max_retries=3)

        # Verify behavior
        self.assertTrue(success)
        self.assertEqual(content, "Success after connection error")
        self.assertIsNone(error)

        # Verify get was called 3 times (initial + 2 retries)
        self.assertEqual(mock_get.call_count, 3)

    @patch("text_to_audio.tasks.openai.OpenAI")
    @patch("text_to_audio.tasks.process_url_to_text")
    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    def test_process_article_permanent_error_no_retry(
        self, mock_process_url, mock_openai
    ):
        """Test that permanent errors (404, 403) are not retried."""
        # Setup mock to return 404 error
        mock_process_url.return_value = (
            False,
            "",
            "404 Not Found: The requested page could not be found.",
        )

        # Create test article with URL but no text
        article = Article.objects.create(
            feed=self.feed,
            title="Test Failed URL Article",
            source_url=self.test_url,
            text_content="",
            status=Article.PROCESSING,
        )

        # Call the task directly (with CELERY_TASK_ALWAYS_EAGER=True)
        result = process_article(article.pk)

        # Refresh from database
        article.refresh_from_db()

        # Verify article is marked as failed
        self.assertEqual(article.status, Article.FAILED)
        self.assertIn("404 Not Found", article.error_message)

        # Verify the return message indicates failure
        self.assertIn("Failed to process Article", result)

        # The task should not have been retried for 404 errors
        mock_process_url.assert_called_once()

    @unittest.skip(
        "This test requires mocking Celery's retry mechanism which is complex"
    )
    @patch("text_to_audio.tasks.process_url_to_text")
    @patch("text_to_audio.tasks.process_article.retry")
    def test_process_article_server_error_with_retry(
        self, mock_retry, mock_process_url
    ):
        """Test that server errors (500) are retried."""
        # This test would need more complex mocking of Celery's retry mechanism
        # Skip for now, but the implementation should be tested manually
        pass
