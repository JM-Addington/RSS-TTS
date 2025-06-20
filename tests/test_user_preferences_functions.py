# flake8: noqa
# mypy: ignore-errors
"""Tests for simple user preference service functions."""

from django.contrib.auth import get_user_model
from django.test import TestCase

from text_to_audio.models import Article, Feed
from text_to_audio.services.user_preferences import UserPreferencesService

User = get_user_model()


class UserPreferencesFunctionsTest(TestCase):
    """Unit tests for basic preference retrieval and saving."""

    def setUp(self):
        """Create user, feed and article."""
        self.user = User.objects.create_user(  # type: ignore[attr-defined]
            username="prefuser", password="pass"
        )
        self.feed = Feed.objects.create(user=self.user, name="Feed")
        self.article = Article.objects.create(feed=self.feed, title="A")
        self.service = UserPreferencesService()

    def test_get_user_preferences_none(self):
        """Returns None when no profile exists."""
        self.assertIsNone(self.service.get_user_preferences(self.user))

    def test_save_and_get_user_preferences(self):
        """Saved preferences are returned correctly."""
        self.service.save_user_preferences(self.user, voice="alloy", speed=1.1)
        prefs = self.service.get_user_preferences(self.user)
        self.assertEqual(prefs, {"voice": "alloy", "speed": 1.1})

    def test_get_article_preferences(self):
        """Article-specific preferences are retrieved."""
        self.article.voice_id = "nova"
        self.article.speed = 1.2
        self.article.save()
        prefs = self.service.get_article_preferences(self.article)
        self.assertEqual(prefs, {"voice": "nova", "speed": 1.2})

    def test_get_feed_voice_mode_default(self):
        """Feed voice mode defaults to auto."""
        self.assertEqual(self.service.get_feed_voice_mode(self.feed), "auto")
