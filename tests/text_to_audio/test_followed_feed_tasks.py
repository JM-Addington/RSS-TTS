from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from text_to_audio.models import Article, Feed, FollowedFeed
from text_to_audio.tasks import import_followed_feeds

User = get_user_model()


class ImportFollowedFeedsTests(TestCase):
    """Tests for the import_followed_feeds task."""

    def setUp(self):
        self.user = User.objects.create_user(username="rssuser", password="pass")
        self.feed = Feed.objects.create(user=self.user, name="Main")

    @patch("text_to_audio.tasks.process_article.delay")
    @patch("text_to_audio.tasks.process_url_to_text")
    @patch("text_to_audio.tasks.feedparser.parse")
    def test_import_creates_articles_with_full_text(
        self, mock_parse, mock_process_url, mock_delay
    ):
        """Feed entries should create articles using fetched full text."""
        entry = SimpleNamespace(
            id="abc1",
            link="https://example.com/a1",
            title="A1",
            summary="summary",
        )
        mock_parse.return_value = SimpleNamespace(entries=[entry])
        mock_process_url.return_value = (True, "full text", None)
        mock_task = MagicMock()
        mock_task.id = "tid"
        mock_delay.return_value = mock_task

        FollowedFeed.objects.create(
            user=self.user,
            url="https://example.com/rss",
            destination_feed=self.feed,
            fetch_full_text=True,
        )

        import_followed_feeds()

        article = Article.objects.get()
        self.assertEqual(article.title, "A1")
        self.assertEqual(article.text_content, "full text")
        self.assertEqual(article.source_url, "https://example.com/a1")
        self.assertEqual(article.feed, self.feed)
        mock_process_url.assert_called_once_with("https://example.com/a1")
        mock_delay.assert_called_once_with(article.pk)

    @patch("text_to_audio.tasks.process_article.delay")
    @patch("text_to_audio.tasks.feedparser.parse")
    def test_import_uses_summary_when_not_fetching(self, mock_parse, mock_delay):
        """When fetch_full_text is False, use summary from feed."""
        entry = SimpleNamespace(
            id="abc2",
            link="https://example.com/a2",
            title="A2",
            summary="summary2",
        )
        mock_parse.return_value = SimpleNamespace(entries=[entry])
        mock_task = MagicMock()
        mock_task.id = "tid2"
        mock_delay.return_value = mock_task

        FollowedFeed.objects.create(
            user=self.user,
            url="https://example.com/rss2",
            destination_feed=self.feed,
            fetch_full_text=False,
        )

        import_followed_feeds()

        article = Article.objects.get(title="A2")
        self.assertEqual(article.text_content, "summary2")
        mock_delay.assert_called_once_with(article.pk)
