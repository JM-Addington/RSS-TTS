"""Tests for the article submission API."""

import json
import uuid
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from text_to_audio.models import Article, Feed

User = get_user_model()


class FeedArticleSubmitAPITests(TestCase):
    """Test the article submission API endpoint."""

    def setUp(self):
        """Set up test data."""
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass123"
        )
        self.feed = Feed.objects.create(user=self.user, name="Test Feed")
        self.url = reverse("api-feed-article-submit", kwargs={"token": self.feed.token})

    @patch("text_to_audio.api_views.process_article")
    def test_submit_text_article(self, mock_process):
        """Test submitting a new article with text content."""
        # Prepare test data
        payload = {
            "title": "Test Article",
            "text_content": "This is test content for the article submission API.",
        }

        # Make API request
        response = self.client.post(
            self.url, data=json.dumps(payload), content_type="application/json"
        )

        # Check response
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.json(), {"success": True})
        self.assertEqual(Article.objects.count(), 1)

        # Verify article data
        article = Article.objects.first()
        self.assertEqual(article.title, "Test Article")
        self.assertEqual(
            article.text_content, "This is test content for the article submission API."
        )
        self.assertEqual(article.feed, self.feed)
        self.assertEqual(article.status, Article.PROCESSING)

        # Verify task was called
        mock_process.delay.assert_called_once_with(article.id)

    @patch("text_to_audio.api_views.process_article")
    def test_submit_url_article(self, mock_process):
        """Test submitting a new article with a URL.

        AIDEV-NOTE: URL fetching is now async - the API returns immediately
        and the Celery task handles URL fetching and title extraction.
        """
        # Prepare test data
        payload = {
            "source_url": "https://example.com/test-article",
        }

        # Make API request
        response = self.client.post(
            self.url, data=json.dumps(payload), content_type="application/json"
        )

        # Check response - should return immediately without fetching URL
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.json(), {"success": True})
        self.assertEqual(Article.objects.count(), 1)

        # Verify article data - URL is saved, content will be fetched async
        article = Article.objects.first()
        self.assertEqual(
            article.title, "Processing..."
        )  # Placeholder until async task runs
        self.assertEqual(article.source_url, "https://example.com/test-article")
        self.assertEqual(article.text_content, "")  # Will be filled by async task
        self.assertEqual(article.feed, self.feed)
        self.assertEqual(article.status, Article.PROCESSING)

        # Verify task was queued (URL fetching happens in task)
        mock_process.delay.assert_called_once_with(article.id)

    @patch("text_to_audio.api_views.process_article")
    def test_submit_url_article_with_title(self, mock_process):
        """Test submitting a URL article with a custom title."""
        # Prepare test data with explicit title
        payload = {
            "source_url": "https://example.com/test-article",
            "title": "My Custom Title",
        }

        # Make API request
        response = self.client.post(
            self.url, data=json.dumps(payload), content_type="application/json"
        )

        # Check response
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        # Verify custom title is preserved
        article = Article.objects.first()
        self.assertEqual(article.title, "My Custom Title")
        self.assertEqual(article.source_url, "https://example.com/test-article")

    def test_submit_both_text_and_url(self):
        """Test that submitting both text and URL fails."""
        # Prepare test data
        payload = {
            "title": "Test Article",
            "text_content": "This is test content.",
            "source_url": "https://example.com/test",
        }

        # Make API request
        response = self.client.post(
            self.url, data=json.dumps(payload), content_type="application/json"
        )

        # Check response
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Article.objects.count(), 0)
        self.assertIn("both text_content and source_url", str(response.json()))

    def test_submit_neither_text_nor_url(self):
        """Test that submitting neither text nor URL fails."""
        # Prepare test data
        payload = {
            "title": "Test Article",
        }

        # Make API request
        response = self.client.post(
            self.url, data=json.dumps(payload), content_type="application/json"
        )

        # Check response
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Article.objects.count(), 0)
        self.assertIn("must provide either", str(response.json()))

    def test_submit_to_nonexistent_feed(self):
        """Test submitting to a feed that doesn't exist."""
        # Generate a random UUID that doesn't match any feed
        random_uuid = uuid.uuid4()
        url = reverse("api-feed-article-submit", kwargs={"token": random_uuid})

        # Prepare test data
        payload = {
            "title": "Test Article",
            "text_content": "This is test content.",
        }

        # Make API request
        response = self.client.post(
            url, data=json.dumps(payload), content_type="application/json"
        )

        # Check response
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(Article.objects.count(), 0)

    @patch("text_to_audio.api_views.process_article")
    def test_submit_with_voice_parameters(self, mock_process):
        """Test submitting an article with voice and speed parameters."""
        # Prepare test data
        payload = {
            "title": "Test Article with Voice",
            "text_content": "This is test content with voice parameters.",
            "voice_id": "nova",
            "speed": 1.2,
        }

        # Make API request
        response = self.client.post(
            self.url, data=json.dumps(payload), content_type="application/json"
        )

        # Check response
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.json(), {"success": True})
        self.assertEqual(Article.objects.count(), 1)

        # Verify article data
        article = Article.objects.first()
        self.assertEqual(article.voice_id, "nova")
        self.assertEqual(article.speed, 1.2)

        # Verify task was called
        mock_process.delay.assert_called_once_with(article.id)
