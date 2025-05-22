"""Tests for the text_to_audio app models."""

# mypy: disable-error-code="attr-defined"
# mypy: disable-error-code="union-attr"

import uuid
from importlib import util

from django.conf import settings
from django.contrib.auth import get_user_model  # type: ignore
from django.db import models
from django.test import TestCase

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
            self.assertTrue(hasattr(Article, "audio_file_path"))
            self.assertTrue(hasattr(Article, "status"))
            self.assertTrue(hasattr(Article, "created_at"))

            # Check field types
            self.assertIsInstance(Article._meta.get_field("feed"), models.ForeignKey)
            self.assertIsInstance(Article._meta.get_field("title"), models.CharField)
            self.assertIsInstance(
                Article._meta.get_field("source_url"), models.URLField
            )
            self.assertIsInstance(
                Article._meta.get_field("text_content"), models.TextField
            )
            self.assertIsInstance(
                Article._meta.get_field("audio_file_path"), models.CharField
            )
            self.assertIsInstance(Article._meta.get_field("status"), models.CharField)
            self.assertIsInstance(
                Article._meta.get_field("created_at"), models.DateTimeField
            )

            # Check field attributes
            self.assertEqual(Article._meta.get_field("feed").related_model, Feed)
            self.assertEqual(Article._meta.get_field("title").max_length, 255)
            self.assertEqual(Article._meta.get_field("audio_file_path").max_length, 255)
            self.assertTrue(Article._meta.get_field("created_at").auto_now_add)

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
        try:
            from text_to_audio.models import Article, Feed

            feed = Feed.objects.create(user=self.user, name="Test Feed")
            article = Article.objects.create(
                feed=feed,
                title="Test Article",
                source_url="https://example.com",
                text_content="Test content",
                audio_file_path="",
                status="PROCESSING",
            )
            self.assertEqual(str(article), "Test Article")
        except ImportError:
            self.fail("Article model does not exist in text_to_audio.models")


# For pytest compatibility
if __name__ == "__main__":
    import pytest

    pytest.main([__file__])
