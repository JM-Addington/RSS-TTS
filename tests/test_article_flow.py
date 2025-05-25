"""Tests for article submission flow in the text_to_audio app."""

# mypy: disable-error-code="attr-defined"

from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import Client, TestCase

from text_to_audio.models import Article, Feed


class TestArticleSubmissionFlow(TestCase):
    """Tests for article submission triggering processing."""

    def setUp(self):
        """Set up test data."""
        self.client = Client()
        self.user = get_user_model().objects.create_user(
            username="flowtester", password="pass123"
        )
        self.feed = Feed.objects.create(user=self.user, name="Default")

    def test_submission_triggers_processing_task(self):
        """Test that article submission triggers the processing task."""
        self.client.login(username="flowtester", password="pass123")
        task_id = "mock-task-id-12345"
        with patch("text_to_audio.views.process_article.delay") as mock_delay:
            # Configure the mock to return a task with an ID
            mock_task = MagicMock()
            mock_task.id = task_id
            mock_delay.return_value = mock_task

            response = self.client.post(
                f"/feeds/{self.feed.pk}/add/",
                {"title": "Flow Test", "text_content": "Sample"},
            )
            self.assertEqual(response.status_code, 302)
            article = Article.objects.get(title="Flow Test")
            self.assertEqual(article.feed, self.feed)
            self.assertEqual(article.status, Article.PROCESSING)
            self.assertEqual(article.celery_task_id, task_id)
            mock_delay.assert_called_once_with(article.id)


# For pytest compatibility
if __name__ == "__main__":
    import pytest

    pytest.main([__file__])
