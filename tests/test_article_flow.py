import unittest
from unittest.mock import patch, MagicMock

from django.contrib.auth import get_user_model
from django.test import Client, TestCase

from text_to_audio.models import Article, Feed
from text_to_audio.tasks import process_article


class TestArticleSubmissionFlow(TestCase):
    """Tests for article submission triggering processing."""

    def setUp(self):
        self.client = Client()
        self.user = get_user_model().objects.create_user(
            username="flowtester", password="pass123"
        )

    def test_submission_triggers_processing_task(self):
        self.client.login(username="flowtester", password="pass123")
        with patch("text_to_audio.views.process_article.delay") as mock_delay:
            response = self.client.post(
                "/articles/submit/",
                {"title": "Flow Test", "text_content": "Sample"},
            )
            self.assertEqual(response.status_code, 302)
            article = Article.objects.get(title="Flow Test")
            self.assertEqual(article.status, Article.PROCESSING)
            mock_delay.assert_called_once_with(article.id)


class TestArticleProcessingTask(TestCase):
    """Tests for article processing task."""

    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="tasktester", password="pass123"
        )
        self.feed = Feed.objects.create(user=self.user, name="Test Feed")
        self.article = Article.objects.create(
            feed=self.feed,
            title="Test Article",
            text_content="Content for testing",
            status=Article.PROCESSING,
        )

    def test_task_error_handling(self):
        # Mock open to raise an exception
        with patch("builtins.open", side_effect=Exception("Test error")):
            # Run the task and catch the exception
            with self.assertRaises(Exception):
                process_article(self.article.id)

            # Reload the article and check if status changed to FAILED
            self.article.refresh_from_db()
            self.assertEqual(self.article.status, Article.FAILED)


if __name__ == "__main__":
    unittest.main()
