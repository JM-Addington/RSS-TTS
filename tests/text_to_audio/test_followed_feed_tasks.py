from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from text_to_audio.models import Article, Feed, FollowedFeed
from text_to_audio.safe_fetch import FetchResult
from text_to_audio.tasks import import_followed_feeds

User = get_user_model()

FEED_BYTES = b"<rss/>"


def fetched(url, **kwargs):
    """Stand-in for safe_fetch.fetch_url (#190): no network, returns fixed bytes."""
    return FetchResult(
        data=FEED_BYTES,
        host="example.com",
        final_host="example.com",
        redirects=0,
        status=200,
        content_type="application/rss+xml",
        content_encoding=None,
        final_url="https://example.com/rss",
    )


def assert_parsed_from_stream(test, mock_parse):
    """feedparser got the fetched bytes as a STREAM (a bytes arg is open()ed as a path) plus the
    final URL as base; never a URL string or raw bytes (M-FEED, M-FEED-STREAM)."""
    mock_parse.assert_called_once()
    source = mock_parse.call_args.args[0]
    test.assertNotIsInstance(source, (str, bytes))
    test.assertEqual(source.read(), FEED_BYTES)
    headers = mock_parse.call_args.kwargs["response_headers"]
    test.assertEqual(headers["content-location"], "https://example.com/rss")
    test.assertEqual(headers["content-type"], "application/rss+xml")


class ImportFollowedFeedsTests(TestCase):
    """Tests for the import_followed_feeds task."""

    def setUp(self):
        self.user = User.objects.create_user(username="rssuser", password="pass")
        self.feed = Feed.objects.create(user=self.user, name="Main")

    @patch("text_to_audio.tasks.fetch_url", side_effect=fetched)
    @patch("text_to_audio.tasks.process_article.delay")
    @patch("text_to_audio.tasks.process_url_to_text")
    @patch("text_to_audio.tasks.feedparser.parse")
    def test_import_creates_articles_with_full_text(
        self, mock_parse, mock_process_url, mock_delay, mock_fetch
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
        self.assertEqual(mock_fetch.call_args.args, ("https://example.com/rss",))
        assert_parsed_from_stream(self, mock_parse)

    @patch("text_to_audio.tasks.fetch_url", side_effect=fetched)
    @patch("text_to_audio.tasks.process_article.delay")
    @patch("text_to_audio.tasks.feedparser.parse")
    def test_import_uses_summary_when_not_fetching(
        self, mock_parse, mock_delay, mock_fetch
    ):
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
        assert_parsed_from_stream(self, mock_parse)
