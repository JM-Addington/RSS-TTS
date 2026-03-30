# flake8: noqa
# mypy: ignore-errors
"""Tests for N+1 query optimization in FeedListView.

AIDEV-NOTE: These tests verify that FeedListView uses annotated querysets
instead of per-feed queries (N+1 problem).
"""

import uuid

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings

from text_to_audio.models import Article, Feed

User = get_user_model()


class FeedListQueryCountTests(TestCase):
    """Tests that FeedListView query count is constant regardless of feed count."""

    def setUp(self):
        self.user = User.objects.create_user(username="querytest", password="testpass")
        self.client = Client()
        self.client.login(username="querytest", password="testpass")

    def _create_feed_with_articles(self, name, num_articles=3):
        """Helper to create a feed with completed articles."""
        feed = Feed.objects.create(user=self.user, name=name)
        for i in range(num_articles):
            Article.objects.create(
                feed=feed,
                title=f"{name} Article {i}",
                status=Article.COMPLETED,
                audio_uuid=uuid.uuid4(),
                audio_duration=300 * (i + 1),
            )
        return feed

    @override_settings(DEBUG=True)
    def test_feed_list_query_count_constant(self):
        """Query count should not grow with number of feeds."""
        from django.db import connection, reset_queries

        # Warm up with 1 feed
        self._create_feed_with_articles("Feed 1")
        reset_queries()
        self.client.get("/feeds/")
        queries_with_1_feed = len(connection.queries)

        # Add 5 more feeds
        for i in range(2, 7):
            self._create_feed_with_articles(f"Feed {i}")

        reset_queries()
        self.client.get("/feeds/")
        queries_with_6_feeds = len(connection.queries)

        # Query count should be constant (not grow with N feeds)
        # Allow a small tolerance for session/auth queries but the key
        # point is it shouldn't scale with feed count
        self.assertLessEqual(
            queries_with_6_feeds,
            queries_with_1_feed + 2,
            f"Query count grew from {queries_with_1_feed} to {queries_with_6_feeds} "
            f"when adding more feeds — likely N+1 problem",
        )

    def test_feed_list_annotations_correct(self):
        """Annotations should match the expected article_count and total_audio_duration."""
        feed1 = Feed.objects.create(user=self.user, name="Feed A")
        # 2 completed articles with durations
        Article.objects.create(
            feed=feed1,
            title="A1",
            status=Article.COMPLETED,
            audio_uuid=uuid.uuid4(),
            audio_duration=600,
        )
        Article.objects.create(
            feed=feed1,
            title="A2",
            status=Article.COMPLETED,
            audio_uuid=uuid.uuid4(),
            audio_duration=1200,
        )
        # 1 processing article (should not count toward duration)
        Article.objects.create(
            feed=feed1,
            title="A3",
            status=Article.PROCESSING,
            audio_uuid=uuid.uuid4(),
            audio_duration=None,
        )
        # 1 failed article (should not count toward duration)
        Article.objects.create(
            feed=feed1,
            title="A4",
            status=Article.FAILED,
            audio_uuid=uuid.uuid4(),
            audio_duration=None,
        )

        feed2 = Feed.objects.create(user=self.user, name="Feed B")
        Article.objects.create(
            feed=feed2,
            title="B1",
            status=Article.COMPLETED,
            audio_uuid=uuid.uuid4(),
            audio_duration=900,
        )

        response = self.client.get("/feeds/")
        feeds = list(response.context["feeds"])

        # Feeds ordered by -created_at, so feed2 is first
        self.assertEqual(feeds[0].name, "Feed B")
        self.assertEqual(feeds[0].article_count, 1)
        self.assertEqual(feeds[0].total_audio_duration, 900)

        self.assertEqual(feeds[1].name, "Feed A")
        self.assertEqual(feeds[1].article_count, 4)  # All articles, any status
        self.assertEqual(feeds[1].total_audio_duration, 1800)  # Only COMPLETED

    def test_feed_list_empty_feeds(self):
        """Feed with no articles should have article_count=0 and total_audio_duration=0."""
        Feed.objects.create(user=self.user, name="Empty Feed")

        response = self.client.get("/feeds/")
        feeds = response.context["feeds"]
        self.assertEqual(feeds[0].article_count, 0)
        self.assertEqual(feeds[0].total_audio_duration, 0)

    def test_feed_list_null_audio_duration(self):
        """Articles with audio_duration=None should not break aggregation."""
        feed = Feed.objects.create(user=self.user, name="Null Duration Feed")
        Article.objects.create(
            feed=feed,
            title="Has Duration",
            status=Article.COMPLETED,
            audio_uuid=uuid.uuid4(),
            audio_duration=500,
        )
        Article.objects.create(
            feed=feed,
            title="No Duration",
            status=Article.COMPLETED,
            audio_uuid=uuid.uuid4(),
            audio_duration=None,
        )

        response = self.client.get("/feeds/")
        feeds = response.context["feeds"]
        self.assertEqual(feeds[0].total_audio_duration, 500)
        self.assertEqual(feeds[0].article_count, 2)
