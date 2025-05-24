"""Tests specifically for OpenAIUsageStats model."""

from django.contrib.auth import get_user_model
from django.test import TestCase

from text_to_audio.models import Article, Feed, OpenAIUsageStats

User = get_user_model()


class OpenAIUsageStatsTests(TestCase):
    """Tests for the OpenAIUsageStats model."""

    def setUp(self):
        """Set up test data."""
        # Get the User model and create a test user
        user_model = get_user_model()
        self.user = user_model.objects.create_user(  # type: ignore
            username="statsuser", email="stats@example.com", password="testpass123"
        )
        self.feed = Feed.objects.create(user=self.user, name="Stats Feed")
        self.article = Article.objects.create(
            feed=self.feed,
            title="Stats Article",
            text_content="Some text for stats.",
            status=Article.PROCESSING,
        )

    def test_create_stats_with_article(self):
        """Test creating an OpenAIUsageStats instance with an article."""
        stats = OpenAIUsageStats.objects.create(
            user=self.user,
            article=self.article,
            tokens_used=100,
            processing_time_ms=500,
            word_count=50,
        )
        self.assertEqual(stats.user, self.user)
        self.assertEqual(stats.article, self.article)
        self.assertEqual(stats.tokens_used, 100)
        self.assertEqual(stats.processing_time_ms, 500)
        self.assertEqual(stats.word_count, 50)
        self.assertIsNotNone(stats.request_timestamp)

    def test_create_stats_without_article(self):
        """Test creating an OpenAIUsageStats instance without an article."""
        stats = OpenAIUsageStats.objects.create(
            user=self.user,
            article=None,
            tokens_used=200,
            processing_time_ms=600,
            word_count=60,
        )
        self.assertEqual(stats.user, self.user)
        self.assertIsNone(stats.article)
        self.assertEqual(stats.tokens_used, 200)
        self.assertEqual(stats.processing_time_ms, 600)
        self.assertEqual(stats.word_count, 60)
        self.assertIsNotNone(stats.request_timestamp)

    def test_str_method(self):
        """Test the OpenAIUsageStats model's __str__ method."""
        stats = OpenAIUsageStats.objects.create(
            user=self.user,
            article=self.article,
            tokens_used=100,
            processing_time_ms=500,
            word_count=50,
        )
        self.assertIn(f"Usage for {self.user.username}", str(stats))
        self.assertIn("at", str(stats))
