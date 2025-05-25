"""Tests for checking and handling stale articles."""

from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone

from text_to_audio.models import Article, Feed
from text_to_audio.tasks import check_stale_articles

User = get_user_model()


class CheckStaleArticlesTests(TestCase):
    """Tests for the check_stale_articles periodic task."""

    def setUp(self):
        """Set up test data."""
        # Type ignore for mypy since it doesn't recognize create_user on User model
        self.user = User.objects.create_user(  # type: ignore
            username="teststaleuser", password="password"
        )
        self.feed = Feed.objects.create(user=self.user, name="Test Feed")

        # Create a recent article in processing state
        self.recent_article = Article.objects.create(
            feed=self.feed,
            title="Recent Article",
            text_content="This is a recent article still processing",
            status=Article.PROCESSING,
            celery_task_id="recent-task-id-123",
        )

        # Create an old article in processing state (will be considered stale)
        self.stale_article = Article.objects.create(
            feed=self.feed,
            title="Stale Article",
            text_content="This is a stale article stuck in processing",
            status=Article.PROCESSING,
            celery_task_id="stale-task-id-456",
        )

        # Manually set the updated_at time to be older than the timeout
        old_time = timezone.now() - timedelta(seconds=3700)  # 1 hour + 100 seconds
        Article.objects.filter(pk=self.stale_article.pk).update(updated_at=old_time)

        # Refresh from database to get the updated timestamp
        self.stale_article.refresh_from_db()

    @override_settings(ARTICLE_PROCESSING_TIMEOUT_SECONDS=3600)  # 1 hour
    @patch("text_to_audio.tasks.celery_app.control.revoke")
    def test_check_stale_articles_marks_stale_as_failed(self, mock_revoke):
        """Test that check_stale_articles identifies and marks stale articles as failed."""  # noqa: E501
        # Call the task
        result = check_stale_articles()

        # Refresh articles from database
        self.recent_article.refresh_from_db()
        self.stale_article.refresh_from_db()

        # Recent article should still be processing
        self.assertEqual(self.recent_article.status, Article.PROCESSING)
        self.assertEqual(self.recent_article.celery_task_id, "recent-task-id-123")

        # Stale article should be marked as failed
        self.assertEqual(self.stale_article.status, Article.FAILED)
        self.assertIsNone(self.stale_article.celery_task_id)
        self.assertIn("Processing timed out", self.stale_article.error_message)

        # Check that Celery task revocation was attempted
        mock_revoke.assert_called_once_with("stale-task-id-456", terminate=True)

        # Verify the return message
        self.assertIn("Checked for stale articles", result)

    @override_settings(ARTICLE_PROCESSING_TIMEOUT_SECONDS=3600)  # 1 hour
    @patch(
        "text_to_audio.tasks.celery_app.control.revoke",
        side_effect=Exception("Revoke error"),
    )
    def test_check_stale_articles_handles_revoke_failure(self, mock_revoke):
        """Test that check_stale_articles continues even if task revocation fails."""
        # Call the task
        result = check_stale_articles()

        # Refresh the stale article from database
        self.stale_article.refresh_from_db()

        # Stale article should still be marked as failed despite revocation error
        self.assertEqual(self.stale_article.status, Article.FAILED)
        self.assertIsNone(self.stale_article.celery_task_id)
        self.assertIn("Processing timed out", self.stale_article.error_message)

        # Check that Celery task revocation was attempted
        mock_revoke.assert_called_once_with("stale-task-id-456", terminate=True)

        # Verify the return message
        self.assertIn("Checked for stale articles", result)

    @override_settings(ARTICLE_PROCESSING_TIMEOUT_SECONDS=3600)  # 1 hour
    def test_check_stale_articles_no_stale_articles(self):
        """Test behavior when no stale articles are found."""
        # Mark the stale article as completed so there are no stale articles
        self.stale_article.status = Article.COMPLETED
        self.stale_article.save()

        # Call the task
        result = check_stale_articles()

        # Verify the return message
        self.assertIn("Checked for stale articles", result)

    @override_settings()  # Remove ARTICLE_PROCESSING_TIMEOUT_SECONDS setting
    @patch("text_to_audio.tasks.celery_app.control.revoke")
    def test_check_stale_articles_with_missing_setting(self, mock_revoke):
        """Test that a default timeout is used if the setting is not defined."""
        # Remove the setting from settings if it exists
        from django.conf import settings

        original_timeout = getattr(settings, "ARTICLE_PROCESSING_TIMEOUT_SECONDS", None)
        if hasattr(settings, "ARTICLE_PROCESSING_TIMEOUT_SECONDS"):
            delattr(settings._wrapped, "ARTICLE_PROCESSING_TIMEOUT_SECONDS")

        try:
            # Call the task
            result = check_stale_articles()

            # Refresh the stale article from database
            self.stale_article.refresh_from_db()

            # Stale article should still be marked as failed using default timeout
            self.assertEqual(self.stale_article.status, Article.FAILED)
            self.assertIsNone(self.stale_article.celery_task_id)

            # Verify the return message mentions the timeout
            self.assertIn("Checked for stale articles", result)

        finally:
            # Restore the original setting if it existed
            if original_timeout is not None:
                settings._wrapped.ARTICLE_PROCESSING_TIMEOUT_SECONDS = original_timeout
