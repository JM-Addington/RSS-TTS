"""Tests for article submission flow in the text_to_audio app."""
# mypy: disable-error-code="attr-defined"

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import Client, TestCase

from text_to_audio.models import Article


class TestArticleSubmissionFlow(TestCase):
    """Tests for article submission triggering processing."""

    def setUp(self):
        """Set up test data."""
        self.client = Client()
        self.user = get_user_model().objects.create_user(
            username="flowtester", password="pass123"
        )

    def test_submission_triggers_processing_task(self):
        """Test that article submission triggers the processing task."""
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


# For pytest compatibility
if __name__ == "__main__":
    import pytest

    pytest.main([__file__])
