# flake8: noqa
# mypy: ignore-errors
"""Tests for N+1 query optimization in article_voice_settings view.

AIDEV-NOTE: Verifies that article_voice_settings uses select_related
for voice_preset and feed to avoid extra queries.
"""

from django.contrib.auth import get_user_model
from django.db import connection, reset_queries
from django.test import Client, TestCase, override_settings

from text_to_audio.models import Article, Feed, UserVoicePreset

User = get_user_model()


class ArticleVoiceSettingsQueryCountTests(TestCase):
    """Tests that article_voice_settings doesn't issue extra queries for voice_preset/feed."""

    def setUp(self):
        self.user = User.objects.create_user(username="querytest", password="testpass")
        self.client = Client()
        self.client.login(username="querytest", password="testpass")
        self.feed = Feed.objects.create(user=self.user, name="Test Feed")
        self.preset = UserVoicePreset.objects.create(
            user=self.user,
            name="Test Preset",
            voice_id="alloy",
            speed=1.0,
        )

    @override_settings(DEBUG=True)
    def test_no_extra_query_for_voice_preset(self):
        """Accessing article.voice_preset should not cause an extra query."""
        article = Article.objects.create(
            feed=self.feed,
            title="Test Article",
            voice_preset=self.preset,
        )

        reset_queries()
        response = self.client.get(f"/articles/{article.id}/voice/")
        queries = list(connection.queries)

        self.assertEqual(response.status_code, 200)

        # Check that no standalone query fetches a single voice_preset by ID
        # (N+1 pattern). A query listing all user presets for the form dropdown
        # is expected; a JOINed article query including voice_preset is fine too.
        voice_preset_n_plus_1 = [
            q for q in queries
            if q["sql"].lower().lstrip().startswith("select")
            and "uservoicepreset" in q["sql"].lower()
            and "text_to_audio_article" not in q["sql"].lower()
            and "user_id" not in q["sql"].lower()
        ]
        self.assertEqual(
            len(voice_preset_n_plus_1),
            0,
            f"Found {len(voice_preset_n_plus_1)} N+1 voice_preset query(ies): "
            f"{voice_preset_n_plus_1}. Should be JOINed via select_related.",
        )

    @override_settings(DEBUG=True)
    def test_no_extra_query_for_feed(self):
        """Accessing article.feed should not cause an extra query after the main fetch."""
        article = Article.objects.create(
            feed=self.feed,
            title="Test Article",
            voice_preset=self.preset,
        )

        reset_queries()
        response = self.client.get(f"/articles/{article.id}/voice/")
        queries = list(connection.queries)

        self.assertEqual(response.status_code, 200)

        # The main article query should JOIN the feed table.
        # There should be no separate feed query beyond the initial article fetch.
        feed_queries = [
            q for q in queries
            if q["sql"].lower().startswith("select")
            and "text_to_audio_feed" in q["sql"].lower()
            and "text_to_audio_article" not in q["sql"].lower()
        ]
        self.assertEqual(
            len(feed_queries),
            0,
            f"Found {len(feed_queries)} separate feed query(ies): "
            f"{feed_queries}. Should be JOINed via select_related.",
        )
