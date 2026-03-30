# flake8: noqa
# mypy: ignore-errors
"""Tests for N+1 query optimization in ArticleDetailView.

AIDEV-NOTE: Verifies that ArticleDetailView uses select_related
for feed and voice_preset to avoid extra queries on GET and POST.
"""

from django.contrib.auth import get_user_model
from django.db import connection, reset_queries
from django.test import Client, TestCase, override_settings

from text_to_audio.models import Article, Feed, UserVoicePreset

User = get_user_model()


class ArticleDetailQueryCountTests(TestCase):
    """Tests that ArticleDetailView doesn't issue extra queries for feed."""

    def setUp(self):
        self.user = User.objects.create_user(username="querytest", password="testpass")
        self.client = Client()
        self.client.login(username="querytest", password="testpass")
        self.feed = Feed.objects.create(user=self.user, name="Test Feed")
        self.article = Article.objects.create(
            feed=self.feed,
            title="Test Article",
            text_content="Some content",
        )

    @override_settings(DEBUG=True)
    def test_no_extra_query_for_feed_on_get(self):
        """GET article detail should JOIN feed via select_related, no separate feed query."""
        reset_queries()
        response = self.client.get(f"/articles/{self.article.id}/detail/")
        queries = list(connection.queries)

        self.assertEqual(response.status_code, 200)

        # There should be no separate feed query — it should be JOINed
        feed_queries = [
            q for q in queries
            if q["sql"].lower().lstrip().startswith("select")
            and "text_to_audio_feed" in q["sql"].lower()
            and "text_to_audio_article" not in q["sql"].lower()
        ]
        self.assertEqual(
            len(feed_queries),
            0,
            f"Found {len(feed_queries)} separate feed query(ies): "
            f"{feed_queries}. Should be JOINed via select_related.",
        )

    @override_settings(DEBUG=True)
    def test_no_extra_query_for_feed_on_post(self):
        """POST to article detail should not have separate feed query."""
        reset_queries()
        response = self.client.post(
            f"/articles/{self.article.id}/detail/",
            {
                "title": "Updated Title",
                "text_content": "Updated content",
            },
        )
        queries = list(connection.queries)

        # POST redirects on success or re-renders on failure — either is fine
        self.assertIn(response.status_code, [200, 302])

        feed_queries = [
            q for q in queries
            if q["sql"].lower().lstrip().startswith("select")
            and "text_to_audio_feed" in q["sql"].lower()
            and "text_to_audio_article" not in q["sql"].lower()
        ]
        self.assertEqual(
            len(feed_queries),
            0,
            f"Found {len(feed_queries)} separate feed query(ies): "
            f"{feed_queries}. Should be JOINed via select_related.",
        )


class ArticleDetailVoicePresetQueryCountTests(TestCase):
    """Tests that ArticleDetailView doesn't issue extra queries for voice_preset."""

    def setUp(self):
        self.user = User.objects.create_user(username="vpquerytest", password="testpass")
        self.client = Client()
        self.client.login(username="vpquerytest", password="testpass")
        self.feed = Feed.objects.create(user=self.user, name="Test Feed")
        self.voice_preset = UserVoicePreset.objects.create(
            user=self.user,
            name="Test Voice",
            voice_id="alloy",
        )
        self.article = Article.objects.create(
            feed=self.feed,
            title="Test Article",
            text_content="Some content",
            voice_preset=self.voice_preset,
        )

    @override_settings(DEBUG=True)
    def test_no_extra_query_for_voice_preset_on_get(self):
        """GET article detail should JOIN voice_preset via select_related."""
        reset_queries()
        response = self.client.get(f"/articles/{self.article.id}/detail/")
        queries = list(connection.queries)

        self.assertEqual(response.status_code, 200)

        # No separate voice_preset query — should be JOINed
        vp_queries = [
            q for q in queries
            if q["sql"].lower().lstrip().startswith("select")
            and "uservoicepreset" in q["sql"].lower()
            and "text_to_audio_article" not in q["sql"].lower()
        ]
        self.assertEqual(
            len(vp_queries),
            0,
            f"Found {len(vp_queries)} separate voice_preset query(ies): "
            f"{vp_queries}. Should be JOINed via select_related.",
        )

    @override_settings(DEBUG=True)
    def test_no_extra_query_for_voice_preset_on_post(self):
        """POST to article detail should not have separate voice_preset query."""
        reset_queries()
        response = self.client.post(
            f"/articles/{self.article.id}/detail/",
            {
                "title": "Updated Title",
                "text_content": "Updated content",
            },
        )
        queries = list(connection.queries)

        self.assertIn(response.status_code, [200, 302])

        vp_queries = [
            q for q in queries
            if q["sql"].lower().lstrip().startswith("select")
            and "uservoicepreset" in q["sql"].lower()
            and "text_to_audio_article" not in q["sql"].lower()
        ]
        self.assertEqual(
            len(vp_queries),
            0,
            f"Found {len(vp_queries)} separate voice_preset query(ies): "
            f"{vp_queries}. Should be JOINed via select_related.",
        )
