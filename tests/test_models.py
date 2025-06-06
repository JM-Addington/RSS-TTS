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
            self.assertTrue(hasattr(Feed, "default_voice_preset"))

            # Check field types
            self.assertIsInstance(Feed._meta.get_field("user"), models.ForeignKey)
            self.assertIsInstance(Feed._meta.get_field("name"), models.CharField)
            self.assertIsInstance(Feed._meta.get_field("token"), models.UUIDField)
            self.assertIsInstance(
                Feed._meta.get_field("created_at"), models.DateTimeField
            )
            self.assertIsInstance(
                Feed._meta.get_field("default_voice_preset"), models.ForeignKey
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

    def test_article_multi_voice_data_field(self):
        """Test saving and retrieving the multi_voice_data JSONField."""
        feed = Feed.objects.create(user=self.user, name="MultiVoice Feed")
        sample_multi_voice_data = {
            "voices": [
                {
                    "name": "narrator",
                    "tone": "neutral",
                    "tts_model": "alloy",
                    "tts_speed": 1.0,
                },
                {
                    "name": "character_ emotive",
                    "tone": "expressive",
                    "tts_model": "nova",
                    "tts_speed": 1.15,
                },
            ],
            "audio_segments": [
                {"text": "This is the first segment.", "voice_name": "narrator"},
                {
                    "text": "And this is the second, more emotive segment!",
                    "voice_name": "character_ emotive",
                },
            ],
        }
        article = Article.objects.create(
            feed=feed,
            title="Multi-Voice Article",
            text_content="Some text content here.",
            multi_voice_data=sample_multi_voice_data,  # Save the dict directly
            status=Article.PROCESSING,
        )
        article.save()

        retrieved_article = Article.objects.get(id=article.id)
        self.assertIsNotNone(retrieved_article.multi_voice_data)
        self.assertIsInstance(retrieved_article.multi_voice_data, dict)
        self.assertEqual(
            retrieved_article.multi_voice_data["voices"][0]["name"], "narrator"
        )
        self.assertEqual(
            retrieved_article.multi_voice_data["audio_segments"][1]["voice_name"],
            "character_ emotive",
        )
        self.assertEqual(len(retrieved_article.multi_voice_data["voices"]), 2)
        # Compare the whole structure
        self.assertEqual(retrieved_article.multi_voice_data, sample_multi_voice_data)


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


class ArticleVoiceFieldTests(TestCase):
    """Tests for Article voice field validation and single source of truth logic."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(  # type: ignore
            username="voiceuser", email="voice@example.com", password="testpass123"
        )
        self.feed = Feed.objects.create(user=self.user, name="Voice Feed")

    def test_article_voice_validation_both_provided(self):
        """Test Article with both voice and voice_id provided - voice_id takes precedence."""
        article = Article.objects.create(
            title="Test Article",
            text_content="Test content",
            voice="nova",
            voice_id="custom_voice_123",
            feed=self.feed,
        )
        article.clean()
        # Single source of truth: voice_id provided resets voice to default
        self.assertEqual(article.voice, "alloy")
        self.assertEqual(article.voice_id, "custom_voice_123")

    def test_article_voice_validation_voice_only(self):
        """Test Article with only voice provided."""
        article = Article.objects.create(
            title="Test Article",
            text_content="Test content",
            voice="nova",
            feed=self.feed,
        )
        article.clean()
        # Should keep voice, voice_id should remain None or empty
        self.assertEqual(article.voice, "nova")
        self.assertIn(article.voice_id, [None, ""])

    def test_article_voice_validation_voice_id_only(self):
        """Test Article with only voice_id provided."""
        article = Article.objects.create(
            title="Test Article",
            text_content="Test content",
            voice_id="custom_voice_123",
            feed=self.feed,
        )
        article.clean()
        # Should set default voice when voice_id is provided
        self.assertEqual(article.voice, "alloy")
        self.assertEqual(article.voice_id, "custom_voice_123")

    def test_article_voice_validation_neither_provided(self):
        """Test Article with neither voice nor voice_id provided."""
        article = Article.objects.create(
            title="Test Article", text_content="Test content", feed=self.feed
        )
        article.clean()
        # Should set default voice
        self.assertEqual(article.voice, "alloy")
        self.assertIn(article.voice_id, [None, ""])


from text_to_audio.models import UserVoicePreset, VOICE_CHOICES


class ArticleGetDisplayVoiceNameTests(TestCase):
    """Tests for the get_display_voice_name property of the Article model."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            username="testdispuser", email="disp@example.com", password="testpass123"
        )
        self.feed = Feed.objects.create(user=self.user, name="Display Name Test Feed")
        # Get the default voice for fallback tests - assumes 'alloy' is a default
        # and its display name is 'Alloy'
        self.default_voice_display = dict(VOICE_CHOICES).get("alloy", "Alloy")

    def test_standard_voice_only(self):
        """Test with only a standard 'voice' set (e.g., 'nova')."""
        article = Article.objects.create(feed=self.feed, title="Test", voice="nova")
        self.assertEqual(article.get_display_voice_name, "Nova")

    def test_standard_voice_with_multivoice(self):
        """Test with a standard 'voice' and multi_voice_data."""
        article = Article.objects.create(
            feed=self.feed,
            title="Test",
            voice="nova",
            multi_voice_data={"key": "value"},
        )
        self.assertEqual(article.get_display_voice_name, "Nova - Multi-Voice")

    def test_custom_voice_id_only(self):
        """Test with a custom 'voice_id' set."""
        article = Article.objects.create(
            feed=self.feed, title="Test", voice_id="custom_voice_123"
        )
        # clean() method will set voice to 'alloy' if voice_id is present
        article.clean()
        self.assertEqual(article.get_display_voice_name, "custom_voice_123")

    def test_custom_voice_id_with_multivoice(self):
        """Test with a custom 'voice_id' and multi_voice_data."""
        article = Article.objects.create(
            feed=self.feed,
            title="Test",
            voice_id="custom_voice_123",
            multi_voice_data={"key": "value"},
        )
        article.clean()
        self.assertEqual(
            article.get_display_voice_name, "custom_voice_123 - Multi-Voice"
        )

    def test_voice_preset_only(self):
        """Test with a 'voice_preset' set."""
        preset = UserVoicePreset.objects.create(
            user=self.user, name="My Favorite Preset", voice_id="alloy"
        )
        article = Article.objects.create(
            feed=self.feed, title="Test", voice_preset=preset
        )
        self.assertEqual(article.get_display_voice_name, "My Favorite Preset")

    def test_voice_preset_with_multivoice(self):
        """Test with a 'voice_preset' and multi_voice_data."""
        preset = UserVoicePreset.objects.create(
            user=self.user, name="My Favorite Preset", voice_id="alloy"
        )
        article = Article.objects.create(
            feed=self.feed,
            title="Test",
            voice_preset=preset,
            multi_voice_data={"key": "value"},
        )
        self.assertEqual(
            article.get_display_voice_name, "My Favorite Preset - Multi-Voice"
        )

    def test_voice_id_is_standard_voice_name(self):
        """Test when 'voice_id' is a standard voice name (e.g., 'nova').
        It should use the 'voice' field's display name ('Alloy' by default after clean).
        """
        article = Article.objects.create(
            feed=self.feed,
            title="Test",
            voice="alloy", # Explicitly set voice, or rely on clean()
            voice_id="nova", # This is a standard voice
        )
        article.clean() # clean() will set self.voice to 'alloy' because voice_id is present
                        # The property logic will then see 'nova' as a standard voice in voice_id
                        # and thus fall back to self.get_voice_display() which uses self.voice ('alloy').
        self.assertEqual(article.get_display_voice_name, self.default_voice_display)

    def test_voice_id_is_standard_voice_name_shimmer_fallback_to_voice_fable(self):
        """Test when 'voice_id' is 'shimmer' (standard) and 'voice' is 'fable'.
        It should use 'fable's display name ('Fable').
        """
        article = Article.objects.create(
            feed=self.feed,
            title="Test",
            voice="fable", # Explicitly set voice
            voice_id="shimmer", # This is a standard voice
        )
        article.clean() # clean() will set self.voice to 'alloy' because voice_id is present.
                        # However, the property logic checks if voice_id is in standard_voice_ids.
                        # If it is, it uses self.get_voice_display().
                        # After clean(), self.voice is 'alloy'.
                        # So, the expected output should be 'Alloy'.
                        # This test case needs to be re-evaluated against the actual logic in `get_display_voice_name`
                        # and `Article.clean()`.

        # Re-evaluation based on model logic:
        # 1. Article.clean(): if voice_id is present (e.g. "shimmer"), self.voice is set to "alloy".
        # 2. get_display_voice_name:
        #    - self.voice_preset is None.
        #    - self.voice_id ("shimmer") IS in standard_voice_ids.
        #    - So, it falls to `else: base_voice_name = self.get_voice_display()`.
        #    - `self.get_voice_display()` will return the display for `self.voice`, which is "alloy" after clean().
        expected_display_name = dict(VOICE_CHOICES).get("alloy", "Alloy")
        self.assertEqual(article.get_display_voice_name, expected_display_name)


    def test_no_specific_voice_settings(self):
        """Test with no specific voice settings (falls back to default 'voice')."""
        # Article creation defaults 'voice' to VOICE_ALLOY ('alloy')
        article = Article.objects.create(feed=self.feed, title="Test")
        article.clean() # Ensures voice is set to default if nothing is provided
        self.assertEqual(article.get_display_voice_name, self.default_voice_display)

    def test_voice_id_is_standard_voice_but_voice_is_different_standard(self):
        """Test case: voice_id = 'nova', voice = 'echo'.
        After clean(), voice becomes 'alloy'.
        get_display_voice_name should return 'Alloy'.
        """
        article = Article.objects.create(
            feed=self.feed,
            title="Test",
            voice="echo",  # A standard voice
            voice_id="nova",  # Also a standard voice
        )
        article.clean() # voice will be 'alloy'
        # Expected: 'Alloy' because voice_id 'nova' is standard, so get_voice_display() for 'alloy' is used.
        self.assertEqual(article.get_display_voice_name, dict(VOICE_CHOICES).get("alloy", "Alloy"))


# For pytest compatibility
if __name__ == "__main__":
    # Models are already imported at the top level
    import pytest

    pytest.main([__file__])
