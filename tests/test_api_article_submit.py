"""Tests for the article submission API."""

import uuid
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import Client, TestCase

from text_to_audio.models import Article, Feed


class ArticleSubmissionAPITests(TestCase):
    """Tests for submitting articles via API."""

    def setUp(self):
        self.client = Client()
        self.user = get_user_model().objects.create_user(
            username="apitester", password="pass123"
        )
        self.feed = Feed.objects.create(user=self.user, name="API Feed")

    def _post(self, payload, token=None):
        token = token or self.feed.token
        return self.client.post(
            f"/api/v1/feeds/{token}/articles/",
            payload,
            content_type="application/json",
        )

    @patch("text_to_audio.api_views.process_article.delay")
    def test_submit_text(self, mock_delay):
        mock_task = MagicMock()
        mock_task.id = "task-text"
        mock_delay.return_value = mock_task

        response = self._post({"text": "Hello"})

        self.assertEqual(response.status_code, 201)
        article = Article.objects.get(feed=self.feed)
        self.assertEqual(article.text_content, "Hello")
        self.assertEqual(article.source_url, "")
        self.assertEqual(article.celery_task_id, "task-text")
        mock_delay.assert_called_once_with(article.id)

    @patch("text_to_audio.api_views.process_article.delay")
    def test_submit_url(self, mock_delay):
        mock_task = MagicMock()
        mock_task.id = "task-url"
        mock_delay.return_value = mock_task

        response = self._post({"url": "https://example.com"})

        self.assertEqual(response.status_code, 201)
        article = Article.objects.get(feed=self.feed)
        self.assertEqual(article.source_url, "https://example.com")
        self.assertEqual(article.text_content, "")
        mock_delay.assert_called_once_with(article.id)

    def test_invalid_token_returns_404(self):
        invalid = uuid.uuid4()
        response = self._post({"text": "test"}, token=invalid)
        self.assertEqual(response.status_code, 404)
        self.assertEqual(Article.objects.count(), 0)

    def test_must_provide_exactly_one_field(self):
        response = self._post({"text": "a", "url": "b"})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Article.objects.count(), 0)
