# flake8: noqa
# mypy: ignore-errors
"""Tests for audio duration functionality."""

import uuid

from django.contrib.auth import get_user_model
from django.test import Client, TestCase

from text_to_audio.models import Article, Feed
from text_to_audio.templatetags.duration_filters import format_duration

User = get_user_model()


class FormatDurationFilterTests(TestCase):
    """Tests for the format_duration template filter."""

    def test_format_duration_hours_and_minutes(self):
        """Test formatting with hours and minutes."""
        # 2 hours and 30 minutes = 9000 seconds
        self.assertEqual(format_duration(9000), "2h 30m")

    def test_format_duration_hours_only(self):
        """Test formatting with only hours (no minutes)."""
        # 2 hours exactly = 7200 seconds
        self.assertEqual(format_duration(7200), "2h")

    def test_format_duration_minutes_only(self):
        """Test formatting with only minutes."""
        # 45 minutes = 2700 seconds
        self.assertEqual(format_duration(2700), "45m")

    def test_format_duration_less_than_minute(self):
        """Test formatting with less than a minute."""
        self.assertEqual(format_duration(30), "<1m")

    def test_format_duration_none(self):
        """Test formatting with None value."""
        self.assertEqual(format_duration(None), "")

    def test_format_duration_zero(self):
        """Test formatting with zero value."""
        self.assertEqual(format_duration(0), "")

    def test_format_duration_string_number(self):
        """Test formatting with string that can be converted to int."""
        self.assertEqual(format_duration("3600"), "1h")

    def test_format_duration_invalid_string(self):
        """Test formatting with invalid string."""
        self.assertEqual(format_duration("not a number"), "")

    def test_format_duration_one_hour_one_minute(self):
        """Test formatting with 1 hour and 1 minute."""
        # 1 hour + 1 minute = 3660 seconds
        self.assertEqual(format_duration(3660), "1h 1m")


class ArticleAudioDurationModelTests(TestCase):
    """Tests for the audio_duration field on Article model."""

    def setUp(self):
        """Create user and feed for tests."""
        self.user = User.objects.create_user(
            username="durationuser", password="testpass"
        )
        self.feed = Feed.objects.create(user=self.user, name="Duration Test Feed")

    def test_audio_duration_field_exists(self):
        """Test that audio_duration field can be set and retrieved."""
        article = Article.objects.create(
            feed=self.feed,
            title="Test Article",
            text_content="Test content",
            status=Article.COMPLETED,
            audio_uuid=uuid.uuid4(),
            audio_duration=300,  # 5 minutes
        )
        self.assertEqual(article.audio_duration, 300)

    def test_audio_duration_can_be_null(self):
        """Test that audio_duration can be null."""
        article = Article.objects.create(
            feed=self.feed,
            title="Test Article",
            text_content="Test content",
            status=Article.COMPLETED,
            audio_uuid=uuid.uuid4(),
            audio_duration=None,
        )
        self.assertIsNone(article.audio_duration)

    def test_audio_duration_query_sum(self):
        """Test summing audio_duration across articles."""
        from django.db.models import Sum

        Article.objects.create(
            feed=self.feed,
            title="Article 1",
            status=Article.COMPLETED,
            audio_uuid=uuid.uuid4(),
            audio_duration=300,
        )
        Article.objects.create(
            feed=self.feed,
            title="Article 2",
            status=Article.COMPLETED,
            audio_uuid=uuid.uuid4(),
            audio_duration=600,
        )
        Article.objects.create(
            feed=self.feed,
            title="Article 3",
            status=Article.PROCESSING,
            audio_uuid=uuid.uuid4(),
            audio_duration=None,  # In-progress, no duration
        )

        total = self.feed.articles.filter(
            status=Article.COMPLETED, audio_duration__isnull=False
        ).aggregate(total=Sum("audio_duration"))["total"]

        self.assertEqual(total, 900)  # 300 + 600


class FeedListViewAudioDurationTests(TestCase):
    """Tests for audio duration display in FeedListView."""

    def setUp(self):
        """Create user, feed and articles for tests."""
        self.user = User.objects.create_user(
            username="feedlistuser", password="testpass"
        )
        self.feed = Feed.objects.create(user=self.user, name="Test Feed")
        self.client = Client()
        self.client.login(username="feedlistuser", password="testpass")

    def test_feed_list_includes_total_audio_duration(self):
        """Test that feed list calculates total audio duration."""
        Article.objects.create(
            feed=self.feed,
            title="Article 1",
            status=Article.COMPLETED,
            audio_uuid=uuid.uuid4(),
            audio_duration=1800,  # 30 minutes
        )
        Article.objects.create(
            feed=self.feed,
            title="Article 2",
            status=Article.COMPLETED,
            audio_uuid=uuid.uuid4(),
            audio_duration=3600,  # 1 hour
        )

        response = self.client.get("/feeds/")
        self.assertEqual(response.status_code, 200)

        # Check that the template context includes total_audio_duration
        feeds = response.context["feeds"]
        self.assertEqual(len(feeds), 1)
        self.assertEqual(feeds[0].total_audio_duration, 5400)  # 1h 30m

    def test_feed_list_handles_no_completed_articles(self):
        """Test that feed list handles feeds with no completed articles."""
        Article.objects.create(
            feed=self.feed,
            title="Article 1",
            status=Article.PROCESSING,
            audio_uuid=uuid.uuid4(),
            audio_duration=None,
        )

        response = self.client.get("/feeds/")
        self.assertEqual(response.status_code, 200)

        feeds = response.context["feeds"]
        self.assertEqual(feeds[0].total_audio_duration, 0)

    def test_feed_list_only_counts_completed_articles(self):
        """Test that only completed articles are counted in duration."""
        Article.objects.create(
            feed=self.feed,
            title="Completed Article",
            status=Article.COMPLETED,
            audio_uuid=uuid.uuid4(),
            audio_duration=1800,
        )
        Article.objects.create(
            feed=self.feed,
            title="Failed Article",
            status=Article.FAILED,
            audio_uuid=uuid.uuid4(),
            audio_duration=None,
        )
        Article.objects.create(
            feed=self.feed,
            title="Processing Article",
            status=Article.PROCESSING,
            audio_uuid=uuid.uuid4(),
            audio_duration=None,
        )

        response = self.client.get("/feeds/")
        self.assertEqual(response.status_code, 200)

        feeds = response.context["feeds"]
        self.assertEqual(feeds[0].total_audio_duration, 1800)

    def test_feed_list_displays_formatted_duration(self):
        """Test that the template displays formatted duration."""
        Article.objects.create(
            feed=self.feed,
            title="Article",
            status=Article.COMPLETED,
            audio_uuid=uuid.uuid4(),
            audio_duration=5400,  # 1h 30m
        )

        response = self.client.get("/feeds/")
        self.assertEqual(response.status_code, 200)

        # Check that the formatted duration appears in the response
        self.assertContains(response, "1h 30m")
