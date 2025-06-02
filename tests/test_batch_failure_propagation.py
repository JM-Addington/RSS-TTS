"""Test for batch failure propagation in process_large_article_batched."""

from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from text_to_audio.models import Article, Feed
from text_to_audio.parallel_tasks import process_large_article_batched

User = get_user_model()


class BatchFailurePropagationTests(TestCase):
    """Test that batch processing correctly propagates finalization failures."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass123"
        )
        self.feed = Feed.objects.create(user=self.user, name="Test Feed")
        self.article = Article.objects.create(
            feed=self.feed,
            title="Test Article",
            text_content="This is a test article.",
            status=Article.PROCESSING,
        )

    @patch('text_to_audio.parallel_tasks.stitch_audio_and_finalize')
    @patch('celery.group')
    def test_finalization_failure_propagates_as_exception(self, mock_group, mock_stitch):
        """Test that finalization failures raise exceptions and mark article as FAILED."""
        # Mock successful batch processing
        mock_batch_result = Mock()
        mock_batch_result.get.return_value = [
            (0, "/tmp/chunk_0.mp3", None),
            (1, "/tmp/chunk_1.mp3", None),
        ]
        mock_group.return_value.apply_async.return_value = mock_batch_result

        # Mock finalization to fail
        finalization_error = Exception("Finalization error: disk full")
        mock_finalize_task = Mock()
        mock_finalize_task.get.side_effect = finalization_error
        mock_stitch.apply_async.return_value = mock_finalize_task

        # Mock chunk task signatures
        chunk_signatures = [Mock(), Mock()]

        # Call the task function directly (bypassing Celery binding)
        with self.assertRaises(Exception) as context:
            # Create mock self for Celery task and set as first argument
            mock_task_self = Mock()
            process_large_article_batched.__func__(
                mock_task_self,
                chunk_signatures,  # positional
                self.article.id,   # positional
                "test-uuid",       # positional
                2                  # positional
            )

        # Verify the correct exception is raised
        self.assertEqual(str(context.exception), "Finalization error: disk full")

        # Verify article is marked as FAILED
        self.article.refresh_from_db()
        self.assertEqual(self.article.status, Article.FAILED)
        self.assertIn("Audio finalization failed", self.article.error_message)
        self.assertIn("disk full", self.article.error_message)

    @patch('text_to_audio.parallel_tasks.stitch_audio_and_finalize')
    @patch('celery.group')
    def test_successful_finalization_returns_message(self, mock_group, mock_stitch):
        """Test that successful finalization returns the success message."""
        # Mock successful batch processing
        mock_batch_result = Mock()
        mock_batch_result.get.return_value = [
            (0, "/tmp/chunk_0.mp3", None),
            (1, "/tmp/chunk_1.mp3", None),
        ]
        mock_group.return_value.apply_async.return_value = mock_batch_result

        # Mock successful finalization
        success_message = "Article 123 finalized successfully in 1500ms"
        mock_finalize_task = Mock()
        mock_finalize_task.get.return_value = success_message
        mock_stitch.apply_async.return_value = mock_finalize_task

        # Mock chunk task signatures
        chunk_signatures = [Mock(), Mock()]

        # Call the task function directly (bypassing Celery binding)
        mock_task_self = Mock()
        result = process_large_article_batched.__func__(
            mock_task_self,
            chunk_signatures,  # positional
            self.article.id,   # positional
            "test-uuid",       # positional
            2                  # positional
        )

        # Verify success message is returned
        self.assertEqual(result, success_message)

        # Verify article was not marked as failed (stitch_audio_and_finalize would update it to COMPLETED)
        self.article.refresh_from_db()
        self.assertEqual(self.article.status, Article.PROCESSING)  # Still processing since we didn't mock the DB update

    @patch('text_to_audio.parallel_tasks.stitch_audio_and_finalize')
    @patch('celery.group')
    def test_no_successful_chunks_raises_exception(self, mock_group, mock_stitch):
        """Test that having no successful chunks raises an exception."""
        # Mock batch processing with no results
        mock_batch_result = Mock()
        mock_batch_result.get.return_value = []
        mock_group.return_value.apply_async.return_value = mock_batch_result

        # Mock chunk task signatures
        chunk_signatures = [Mock()]

        # Call the task and expect it to raise ValueError
        with self.assertRaises(ValueError) as context:
            mock_task_self = Mock()
            process_large_article_batched.__func__(
                mock_task_self,
                chunk_signatures,  # positional
                self.article.id,   # positional
                "test-uuid",       # positional
                1                  # positional
            )

        # Verify the correct exception is raised
        self.assertEqual(str(context.exception), "No successful chunks to process")

        # Verify article is marked as FAILED
        self.article.refresh_from_db()
        self.assertEqual(self.article.status, Article.FAILED)
        self.assertIn("Batched processing failed", self.article.error_message)
