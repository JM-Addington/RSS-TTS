"""Tests for the text_to_audio app models."""

# mypy: disable-error-code="attr-defined"
# mypy: disable-error-code="union-attr"

import uuid
from importlib import util

from django.conf import settings
from django.contrib.auth import get_user_model  # type: ignore
from django.db import models
from django.test import TestCase

# Import models needed for tests
from text_to_audio.models import Article, Feed, OpenAIUsageStats

User = get_user_model()  # type: ignore


class TestModels(TestCase):
    """Tests for the text_to_audio app models."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(  # type: ignore
            username="testuser", email="test@example.com", password="testpass123"
        )

    def test_models_file_exists(self):
        """Test that the models.py file exists."""
        models_path = f"{settings.BASE_DIR}/text_to_audio/models.py"
        spec = util.find_spec("text_to_audio.models")
        self.assertIsNotNone(spec, f"models.py file does not exist at {models_path}")

    def test_feed_model_exists(self):
        """Test that the Feed model exists and has the required fields."""
        try:
            from text_to_audio.models import Feed

            # Check that Feed model inherits from models.Model
            self.assertTrue(issubclass(Feed, models.Model))

            # Check required fields
            self.assertTrue(hasattr(Feed, "user"))
            self.assertTrue(hasattr(Feed, "name"))
            self.assertTrue(hasattr(Feed, "token"))
            self.assertTrue(hasattr(Feed, "created_at"))

            # Check field types
            self.assertIsInstance(Feed._meta.get_field("user"), models.ForeignKey)
            self.assertIsInstance(Feed._meta.get_field("name"), models.CharField)
            self.assertIsInstance(Feed._meta.get_field("token"), models.UUIDField)
            self.assertIsInstance(
                Feed._meta.get_field("created_at"), models.DateTimeField
            )

            # Check field attributes
            self.assertEqual(Feed._meta.get_field("user").related_model, User)
            self.assertEqual(Feed._meta.get_field("name").max_length, 100)
            self.assertEqual(Feed._meta.get_field("token").default, uuid.uuid4)
            self.assertTrue(Feed._meta.get_field("created_at").auto_now_add)
        except ImportError:
            self.fail("Feed model does not exist in text_to_audio.models")

    def test_article_model_exists(self):
        """Test that the Article model exists and has the required fields."""
        try:
            from text_to_audio.models import Article, Feed

            # Check that Article model inherits from models.Model
            self.assertTrue(issubclass(Article, models.Model))

            # Check required fields
            self.assertTrue(hasattr(Article, "feed"))
            self.assertTrue(hasattr(Article, "title"))
            self.assertTrue(hasattr(Article, "source_url"))
            self.assertTrue(hasattr(Article, "text_content"))
            self.assertTrue(hasattr(Article, "summary"))
            self.assertTrue(hasattr(Article, "audio_file_path"))
            self.assertTrue(hasattr(Article, "status"))
            self.assertTrue(hasattr(Article, "created_at"))
            self.assertTrue(hasattr(Article, "updated_at"))
            self.assertTrue(hasattr(Article, "celery_task_id"))

            # Check field types
            self.assertIsInstance(Article._meta.get_field("feed"), models.ForeignKey)
            self.assertIsInstance(Article._meta.get_field("title"), models.CharField)
            self.assertIsInstance(
                Article._meta.get_field("source_url"), models.URLField
            )
            self.assertIsInstance(
                Article._meta.get_field("text_content"), models.TextField
            )
            self.assertIsInstance(Article._meta.get_field("summary"), models.TextField)
            self.assertIsInstance(
                Article._meta.get_field("audio_file_path"), models.CharField
            )
            self.assertIsInstance(Article._meta.get_field("status"), models.CharField)
            self.assertIsInstance(
                Article._meta.get_field("created_at"), models.DateTimeField
            )
            self.assertIsInstance(
                Article._meta.get_field("updated_at"), models.DateTimeField
            )
            self.assertIsInstance(
                Article._meta.get_field("celery_task_id"), models.CharField
            )

            # Check field attributes
            self.assertEqual(Article._meta.get_field("feed").related_model, Feed)
            self.assertEqual(Article._meta.get_field("title").max_length, 255)
            self.assertEqual(Article._meta.get_field("audio_file_path").max_length, 255)
            self.assertEqual(Article._meta.get_field("celery_task_id").max_length, 255)
            self.assertTrue(Article._meta.get_field("created_at").auto_now_add)
            self.assertTrue(Article._meta.get_field("updated_at").auto_now)

            # Check status choices
            self.assertTrue(hasattr(Article, "STATUS_CHOICES"))
            self.assertIn(("PROCESSING", "Processing"), Article.STATUS_CHOICES)
            self.assertIn(("COMPLETED", "Completed"), Article.STATUS_CHOICES)
            self.assertIn(("FAILED", "Failed"), Article.STATUS_CHOICES)
        except ImportError:
            self.fail("Article model does not exist in text_to_audio.models")

    def test_feed_str_method(self):
        """Test the Feed model's __str__ method."""
        try:
            from text_to_audio.models import Feed

            feed = Feed.objects.create(user=self.user, name="Test Feed")
            self.assertEqual(str(feed), "Test Feed")
        except ImportError:
            self.fail("Feed model does not exist in text_to_audio.models")

    def test_article_str_method(self):
        """Test the Article model's __str__ method."""
        # No try-except needed as imports are at the top
        feed = Feed.objects.create(user=self.user, name="Test Feed")
        article = Article.objects.create(
            feed=feed,
            title="Test Article",
            source_url="https://example.com",
            text_content="Test content",
            audio_file_path="",
            status=Article.PROCESSING,
            celery_task_id=None,
        )
        self.assertEqual(str(article), "Test Article")


class OpenAIUsageStatsModelTests(TestCase):
    """Tests for the OpenAIUsageStats model."""

    def setUp(self):
        """Set up test data."""
        # Type ignore - Django's get_user_model() doesn't expose create_user
        self.user = User.objects.create_user(  # type: ignore
            username="statsuser", email="stats@example.com", password="testpass123"
        )
        self.feed = Feed.objects.create(user=self.user, name="Stats Feed")
        self.article = Article.objects.create(
            feed=self.feed,
            title="Stats Article",
            text_content="Some text for stats.",
            status=Article.PROCESSING,
            celery_task_id=None,
        )
        # OpenAIUsageStats is already imported at the top level

    def test_openai_usage_stats_model_exists(self):
        """Test that the OpenAIUsageStats model exists and has the required fields."""
        self.assertTrue(issubclass(OpenAIUsageStats, models.Model))

        # Check required fields
        self.assertTrue(hasattr(OpenAIUsageStats, "user"))
        self.assertTrue(hasattr(OpenAIUsageStats, "article"))
        self.assertTrue(hasattr(OpenAIUsageStats, "tokens_used"))
        self.assertTrue(hasattr(OpenAIUsageStats, "processing_time_ms"))
        self.assertTrue(hasattr(OpenAIUsageStats, "word_count"))
        self.assertTrue(hasattr(OpenAIUsageStats, "request_timestamp"))

        # Check field types
        self.assertIsInstance(
            OpenAIUsageStats._meta.get_field("user"), models.ForeignKey
        )
        self.assertIsInstance(
            OpenAIUsageStats._meta.get_field("article"), models.ForeignKey
        )
        self.assertIsInstance(
            OpenAIUsageStats._meta.get_field("tokens_used"), models.IntegerField
        )
        self.assertIsInstance(
            OpenAIUsageStats._meta.get_field("processing_time_ms"), models.IntegerField
        )
        self.assertIsInstance(
            OpenAIUsageStats._meta.get_field("word_count"), models.IntegerField
        )
        self.assertIsInstance(
            OpenAIUsageStats._meta.get_field("request_timestamp"), models.DateTimeField
        )

        # Check field attributes
        self.assertEqual(OpenAIUsageStats._meta.get_field("user").related_model, User)
        self.assertEqual(
            OpenAIUsageStats._meta.get_field("article").related_model, Article
        )
        # Check if article can be null
        self.assertTrue(OpenAIUsageStats._meta.get_field("article").null)
        self.assertTrue(
            OpenAIUsageStats._meta.get_field("request_timestamp").auto_now_add
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
        # Format timestamp for comparison with __str__ output
        timestamp_fmt = stats.request_timestamp.strftime("%Y-%m-%d %H:%M:%S")
        expected_str = f"Usage for {self.user.username} at {timestamp_fmt}"
        self.assertEqual(str(stats), expected_str)

    def test_str_method_no_article(self):
        """Test the __str__ method when article is None (should be same)."""
        stats = OpenAIUsageStats.objects.create(
            user=self.user,
            article=None,  # No article
            tokens_used=150,
            processing_time_ms=550,
            word_count=55,
        )
        # Format timestamp for comparison with __str__ output
        timestamp_fmt = stats.request_timestamp.strftime("%Y-%m-%d %H:%M:%S")
        expected_str = f"Usage for {self.user.username} at {timestamp_fmt}"
        self.assertEqual(str(stats), expected_str)


# For pytest compatibility
if __name__ == "__main__":
    # Models are already imported at the top level
    import pytest

    pytest.main([__file__])
