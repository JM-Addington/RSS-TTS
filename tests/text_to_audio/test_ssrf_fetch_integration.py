"""Call-site tests: article fetch, followed feeds and the followed-feed form use the pinned fetch (#190).

AIDEV-NOTE: NetworkTripwire makes any real socket connect fail the test, so a call site that
bypasses safe_fetch (requests, feedparser's urllib) goes red here instead of reaching the network.
"""

import socket
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from text_to_audio.models import Article, Feed, FollowedFeed

User = get_user_model()

PUBLIC_IP = "93.184.216.34"

RSS = b"""<?xml version="1.0"?>
<rss version="2.0"><channel><title>T</title>
<item><guid>g1</guid><title>Entry One</title><link>https://example.com/e1</link>
<description>summary one</description></item>
</channel></rss>"""


def fake_getaddrinfo(table):
    """A getaddrinfo that answers from ``table`` (host -> ip) and records lookups."""
    calls = []

    def _gai(host, port, *args, **kwargs):
        calls.append(host)
        ip = table.get(host, PUBLIC_IP)
        family = socket.AF_INET6 if ":" in ip else socket.AF_INET
        return [(family, socket.SOCK_STREAM, 6, "", (ip, port or 80))]

    _gai.calls = calls  # type: ignore[attr-defined]
    return _gai


class FakeResponse:
    def __init__(self, status=200, headers=None, body=b""):
        self.status = status
        self.headers = headers or {}
        self._body = body

    def stream(self, n):
        if self._body:
            yield self._body

    def release_conn(self):
        pass


class NetworkTripwire(TestCase):
    """Fails any test that opens a real TCP connection."""

    def setUp(self):
        super().setUp()
        self.real_connects = []

        def _no_connect(sock, address):
            self.real_connects.append(address)
            raise AssertionError(f"real network connect attempted to {address!r}")

        patcher = patch.object(socket.socket, "connect", _no_connect)
        patcher.start()
        self.addCleanup(patcher.stop)

    def tearDown(self):
        self.assertEqual(self.real_connects, [])
        super().tearDown()


class FetchUrlContentSSRFTests(NetworkTripwire):
    def _connector(self, *responses):
        calls = []
        queue = list(responses)

        def _connect(**kwargs):
            calls.append(kwargs)
            return queue.pop(0)

        _connect.calls = calls  # type: ignore[attr-defined]
        return _connect

    def test_redirect_to_private_ip_blocked_without_second_connect(self):
        from text_to_audio.utils import fetch_url_content

        connector = self._connector(
            FakeResponse(302, {"Location": "http://10.0.0.1/admin"})
        )
        with patch("socket.getaddrinfo", fake_getaddrinfo({})), patch(
            "text_to_audio.safe_fetch.connect_pinned", connector
        ), patch("text_to_audio.utils.time.sleep"):
            success, content, error = fetch_url_content("http://example.com/")
        self.assertFalse(success)
        self.assertEqual(content, "")
        self.assertIn("URL blocked by security policy", error or "")
        self.assertIn("address_refused", error or "")
        self.assertEqual(len(connector.calls), 1)
        self.assertEqual(connector.calls[0]["ip"], PUBLIC_IP)

    def test_success_decodes_with_charset(self):
        from text_to_audio.utils import fetch_url_content

        body = "<html>café</html>".encode("latin-1")
        connector = self._connector(
            FakeResponse(200, {"Content-Type": "text/html; charset=iso-8859-1"}, body)
        )
        with patch("socket.getaddrinfo", fake_getaddrinfo({})), patch(
            "text_to_audio.safe_fetch.connect_pinned", connector
        ):
            success, content, error = fetch_url_content("https://example.com/a")
        self.assertTrue(success, error)
        self.assertEqual(content, "<html>café</html>")
        self.assertEqual(connector.calls[0]["host"], "example.com")
        self.assertEqual(connector.calls[0]["ip"], PUBLIC_IP)

    def test_oversized_body_blocked(self):
        from text_to_audio.utils import fetch_url_content

        connector = self._connector(
            FakeResponse(200, {"Content-Length": str(10**12)}, b"x")
        )
        with patch("socket.getaddrinfo", fake_getaddrinfo({})), patch(
            "text_to_audio.safe_fetch.connect_pinned", connector
        ):
            success, _, error = fetch_url_content("https://example.com/big")
        self.assertFalse(success)
        self.assertIn("too_large", error or "")
        self.assertEqual(len(connector.calls), 1)


class ImportFollowedFeedsSSRFTests(NetworkTripwire):
    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user(username="ssrfuser", password="pass")
        self.feed = Feed.objects.create(user=self.user, name="Main")

    @patch("text_to_audio.tasks.process_article.delay")
    @patch("text_to_audio.tasks.feedparser.parse")
    def test_private_feed_url_never_handed_to_feedparser(self, mock_parse, mock_delay):
        mock_parse.return_value = SimpleNamespace(entries=[])
        FollowedFeed.objects.create(
            user=self.user,
            url="http://10.0.0.1/rss",
            destination_feed=self.feed,
            fetch_full_text=False,
        )
        from text_to_audio.tasks import import_followed_feeds

        with patch("socket.getaddrinfo", fake_getaddrinfo({})):
            import_followed_feeds()

        for call in mock_parse.call_args_list:
            self.assertIsInstance(call.args[0], bytes, call)
        self.assertFalse(Article.objects.exists())
        mock_delay.assert_not_called()

    @patch("text_to_audio.tasks.process_article.delay")
    def test_public_feed_fetched_pinned_and_parsed_from_bytes(self, mock_delay):
        mock_task = MagicMock()
        mock_task.id = "tid"
        mock_delay.return_value = mock_task
        FollowedFeed.objects.create(
            user=self.user,
            url="https://feeds.example.com/rss",
            destination_feed=self.feed,
            fetch_full_text=False,
        )
        calls = []

        def _connect(**kwargs):
            calls.append(kwargs)
            return FakeResponse(200, {"Content-Type": "application/rss+xml"}, RSS)

        from text_to_audio.tasks import import_followed_feeds

        with patch("socket.getaddrinfo", fake_getaddrinfo({})), patch(
            "text_to_audio.safe_fetch.connect_pinned", _connect
        ):
            import_followed_feeds()

        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["ip"], PUBLIC_IP)
        self.assertEqual(calls[0]["host"], "feeds.example.com")
        article = Article.objects.get()
        self.assertEqual(article.title, "Entry One")
        self.assertEqual(article.source_url, "https://example.com/e1")

    @patch("text_to_audio.tasks.process_article.delay")
    @patch("text_to_audio.tasks.feedparser.parse")
    def test_feed_redirect_to_metadata_refused(self, mock_parse, mock_delay):
        mock_parse.return_value = SimpleNamespace(entries=[])
        FollowedFeed.objects.create(
            user=self.user,
            url="https://feeds.example.com/rss",
            destination_feed=self.feed,
        )
        calls = []

        def _connect(**kwargs):
            calls.append(kwargs)
            return FakeResponse(302, {"Location": "http://169.254.169.254/latest/"})

        from text_to_audio.tasks import import_followed_feeds

        with patch("socket.getaddrinfo", fake_getaddrinfo({})), patch(
            "text_to_audio.safe_fetch.connect_pinned", _connect
        ):
            import_followed_feeds()

        self.assertEqual(len(calls), 1)
        mock_parse.assert_not_called()


class FollowedFeedFormSSRFTests(NetworkTripwire):
    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user(username="formuser", password="pass")
        self.feed = Feed.objects.create(user=self.user, name="Main")

    def _form(self, url):
        from text_to_audio.forms import FollowedFeedForm

        return FollowedFeedForm(
            data={
                "url": url,
                "destination_feed": self.feed.pk,
                "fetch_full_text": False,
                "is_active": True,
            },
            user=self.user,
        )

    def test_private_ip_rejected(self):
        form = self._form("http://10.0.0.1/rss")
        self.assertFalse(form.is_valid())
        self.assertIn("url", form.errors)

    def test_name_resolving_private_rejected(self):
        with patch(
            "socket.getaddrinfo", fake_getaddrinfo({"evil.example": "127.0.0.1"})
        ):
            form = self._form("http://evil.example/rss")
            self.assertFalse(form.is_valid())
        self.assertIn("url", form.errors)

    def test_ftp_rejected(self):
        form = self._form("ftp://example.com/rss")
        self.assertFalse(form.is_valid())
        self.assertIn("url", form.errors)

    def test_public_accepted(self):
        with patch("socket.getaddrinfo", fake_getaddrinfo({})):
            form = self._form("https://example.com/rss")
            self.assertTrue(form.is_valid(), form.errors)
