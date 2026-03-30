# flake8: noqa
# mypy: ignore-errors
"""Tests for N+1 query optimization in FeedArticleListView.

AIDEV-NOTE: Verifies that FeedArticleListView uses select_related('voice_preset')
to avoid N+1 queries when rendering article.get_display_voice_name().
"""

from django.contrib.auth import get_user_model
from django.db import connection, reset_queries
from django.test import Client, TestCase, override_settings

from text_to_audio.models import Article, Feed, UserVoicePreset

User = get_user_model()


class FeedArticleListQueryCountTests(TestCase):
    """Tests that FeedArticleListView query count is constant for voice_preset access."""

    def setUp(self):
        self.user = User.objects.create_user(username="querytest", password="testpass")
        self.client = Client()
        self.client.login(username="querytest", password="testpass")
        self.feed = Feed.objects.create(user=self.user, name="Test Feed")

    @override_settings(DEBUG=True)
    def test_query_count_constant_with_voice_presets(self):
        """Query count should not grow with number of articles that have voice_presets."""
        preset = UserVoicePreset.objects.create(
            user=self.user,
            name="Test Preset",
            voice_id="alloy",
            speed=1.0,
        )

        # Create 1 article with a voice_preset
        Article.objects.create(
            feed=self.feed,
            title="Article 1",
            voice_preset=preset,
        )

        reset_queries()
        self.client.get(f"/feeds/{self.feed.pk}/")
        queries_with_1 = len(connection.queries)

        # Create 5 more articles with voice_presets
        for i in range(2, 7):
            Article.objects.create(
                feed=self.feed,
                title=f"Article {i}",
                voice_preset=preset,
            )

        reset_queries()
        self.client.get(f"/feeds/{self.feed.pk}/")
        queries_with_6 = len(connection.queries)

        # Query count should be constant — not scale with article count
        self.assertLessEqual(
            queries_with_6,
            queries_with_1 + 2,
            f"Query count grew from {queries_with_1} to {queries_with_6} "
            f"when adding more articles with voice_presets — likely N+1 problem",
        )
