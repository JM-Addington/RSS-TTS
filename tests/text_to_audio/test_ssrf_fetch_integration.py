"""Call-site tests: article fetch, followed feeds and the followed-feed form use the pinned fetch (#190).

AIDEV-NOTE: NetworkTripwire makes any real socket connect fail the test, so a call site that
bypasses safe_fetch (requests, feedparser's urllib) goes red here instead of reaching the network.
"""

import gzip
import os
import socket
import tempfile
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.core.exceptions import ValidationError

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

    def _fetch(self, url, *responses, **kwargs):
        from text_to_audio.utils import fetch_url_content

        connector = self._connector(*responses)
        with patch("socket.getaddrinfo", fake_getaddrinfo({})), patch(
            "text_to_audio.safe_fetch.connect_pinned", connector
        ), patch("text_to_audio.utils.time.sleep"):
            return fetch_url_content(url, **kwargs), connector

    def test_too_large_message_is_not_a_security_refusal(self):
        (success, _, error), _ = self._fetch(
            "https://example.com/big",
            FakeResponse(200, {"Content-Length": str(10**12)}, b"x"),
        )
        self.assertFalse(success)
        self.assertIn("too large", error or "")
        self.assertNotIn("security policy", error or "")

    def test_six_mib_article_fetched(self):
        """Real news pages run past 5 MiB uncompressed (9/60 cnn.com links did)."""
        body = b"<html>" + b"a" * (6 * 1024 * 1024) + b"</html>"
        (success, content, error), _ = self._fetch(
            "https://example.com/long",
            FakeResponse(200, {"Content-Type": "text/html; charset=utf-8"}, body),
        )
        self.assertTrue(success, error)
        self.assertEqual(len(content), len(body))

    def test_default_article_cap_is_20_mib(self):
        from django.conf import settings

        from text_to_audio.utils import DEFAULT_ARTICLE_URL_MAX_BYTES

        self.assertEqual(DEFAULT_ARTICLE_URL_MAX_BYTES, 20 * 1024 * 1024)
        if "ARTICLE_URL_MAX_BYTES" not in os.environ:
            self.assertEqual(settings.ARTICLE_URL_MAX_BYTES, 20 * 1024 * 1024)

    def test_redirect_limit_message(self):
        hops = [FakeResponse(302, {"Location": f"/{i}"}) for i in range(12)]
        (success, _, error), _ = self._fetch("https://example.com/", *hops)
        self.assertFalse(success)
        self.assertIn("Too many redirects", error or "")

    def test_malformed_url_returns_tuple_not_raises(self):
        for url in ("http://[::1", "http://[example.com]/", "https://[x/"):
            with self.subTest(url=url):
                (success, content, error), connector = self._fetch(url)
                self.assertFalse(success)
                self.assertEqual(content, "")
                self.assertTrue(error)
                self.assertEqual(connector.calls, [])

    def test_unusable_charset_falls_back_to_utf8(self):
        """idna/punycode/undefined raise UnicodeError (not LookupError) from bytes.decode."""
        for charset in ("idna", "punycode", "undefined"):
            with self.subTest(charset=charset):
                (success, content, error), _ = self._fetch(
                    "https://example.com/a",
                    FakeResponse(
                        200,
                        {"Content-Type": f"text/html; charset={charset}"},
                        "<html>café</html>".encode("utf-8"),
                    ),
                )
                self.assertTrue(success, error)
                self.assertEqual(content, "<html>café</html>")

    def test_compressed_response_refused(self):
        (success, content, error), _ = self._fetch(
            "https://example.com/a",
            FakeResponse(
                200,
                {"Content-Type": "text/html", "Content-Encoding": "gzip"},
                gzip.compress(b"<html>x</html>"),
            ),
        )
        self.assertFalse(success)
        self.assertEqual(content, "")
        self.assertIn("Unsupported content encoding 'gzip'", error or "")

    def test_retry_exhaustion_log_has_host_not_url(self):
        def _refuse(**kwargs):
            raise OSError("refused")

        from text_to_audio.utils import fetch_url_content

        with patch("socket.getaddrinfo", fake_getaddrinfo({})), patch(
            "text_to_audio.safe_fetch.connect_pinned", _refuse
        ), patch("text_to_audio.utils.time.sleep"), self.assertLogs(
            "text_to_audio.utils", level="INFO"
        ) as logs:
            success, _, error = fetch_url_content(
                "https://example.com/a?token=SECRET123", max_retries=2
            )
        self.assertFalse(success)
        self.assertTrue(any("[FETCH-URL-MAXRETRY]" in line for line in logs.output))
        for line in logs.output:
            self.assertNotIn("SECRET123", line)


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
            self.assertTrue(hasattr(call.args[0], "read"), call)
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


ATOM_RELATIVE = b"""<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"><title>A</title><id>urn:a</id>
<entry><id>urn:a:1</id><title>Rel</title><link href="/posts/a"/><summary>s</summary></entry>
</feed>"""


def rss_with_link(guid, title, link):
    return (
        b'<?xml version="1.0"?><rss version="2.0"><channel><title>T</title><item><guid>'
        + guid.encode()
        + b"</guid><title>"
        + title.encode()
        + b"</title><link>"
        + link.encode()
        + b"</link><description>summary of "
        + title.encode()
        + b"</description></item></channel></rss>"
    )


class ImportFollowedFeedsRobustnessTests(NetworkTripwire):
    """One hostile feed must not read local files, nor stop any other user's feed (#190 review)."""

    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user(username="victim", password="pass")
        self.feed = Feed.objects.create(user=self.user, name="Main")
        self.attacker = User.objects.create_user(username="attacker", password="pass")
        self.attacker_feed = Feed.objects.create(user=self.attacker, name="Evil")
        task = MagicMock()
        task.id = "tid"
        patcher = patch("text_to_audio.tasks.process_article.delay", return_value=task)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _follow(self, user, feed, url, **kwargs):
        return FollowedFeed.objects.create(
            user=user, url=url, destination_feed=feed, **kwargs
        )

    def _run(self, by_host):
        """by_host: host -> FakeResponse (or list of them, in order)."""
        calls = []

        def _connect(**kwargs):
            calls.append(kwargs["host"])
            answer = by_host[kwargs["host"]]
            return answer.pop(0) if isinstance(answer, list) else answer

        from text_to_audio.tasks import import_followed_feeds

        with patch("socket.getaddrinfo", fake_getaddrinfo({})), patch(
            "text_to_audio.safe_fetch.connect_pinned", _connect
        ), patch("text_to_audio.utils.time.sleep"):
            import_followed_feeds()
        return calls

    def test_body_naming_a_local_file_is_not_opened(self):
        """feedparser.parse(bytes) open()s a bytes path; the body must reach it as a stream."""
        with tempfile.NamedTemporaryFile("wb", suffix=".xml", delete=False) as fh:
            fh.write(rss_with_link("lf", "LOCAL-FILE-CONTENT", "https://x.example/l"))
        self.addCleanup(os.unlink, fh.name)
        self._follow(self.attacker, self.attacker_feed, "https://evil.example.com/rss")
        self._run(
            {
                "evil.example.com": FakeResponse(
                    200, {"Content-Type": "text/plain"}, fh.name.encode()
                )
            }
        )
        self.assertEqual(
            list(Article.objects.values_list("title", flat=True)), []
        )

    def test_newer_feed_exception_does_not_stop_older_feed(self):
        victim = self._follow(self.user, self.feed, "https://good.example.com/rss")
        self._follow(self.attacker, self.attacker_feed, "https://evil.example.com/rss")
        from text_to_audio import tasks

        real = tasks.fetch_url

        def _fetch(url, **kwargs):
            if "evil" in url:
                raise RuntimeError("unexpected")
            return real(url, **kwargs)

        with patch.object(tasks, "fetch_url", _fetch):
            self._run(
                {
                    "good.example.com": FakeResponse(
                        200,
                        {"Content-Type": "application/rss+xml"},
                        rss_with_link("v1", "Victim", "https://good.example.com/1"),
                    )
                }
            )
        victim.refresh_from_db()
        self.assertIsNotNone(victim.last_checked)
        self.assertEqual(
            list(Article.objects.values_list("title", flat=True)), ["Victim"]
        )

    def test_malformed_redirect_does_not_stop_older_feed(self):
        victim = self._follow(self.user, self.feed, "https://good.example.com/rss")
        self._follow(self.attacker, self.attacker_feed, "https://evil.example.com/rss")
        calls = self._run(
            {
                "evil.example.com": FakeResponse(302, {"Location": "http://[x/"}),
                "good.example.com": FakeResponse(
                    200,
                    {"Content-Type": "application/rss+xml"},
                    rss_with_link("v1", "Victim", "https://good.example.com/1"),
                ),
            }
        )
        self.assertEqual(calls, ["evil.example.com", "good.example.com"])
        victim.refresh_from_db()
        self.assertIsNotNone(victim.last_checked)

    def test_malformed_entry_link_with_full_text_falls_back_to_summary(self):
        victim = self._follow(self.user, self.feed, "https://good.example.com/rss")
        self._follow(
            self.attacker,
            self.attacker_feed,
            "https://evil.example.com/rss",
            fetch_full_text=True,
        )
        self._run(
            {
                "evil.example.com": FakeResponse(
                    200,
                    {"Content-Type": "application/rss+xml"},
                    rss_with_link("e1", "Evil", "http://[::1"),
                ),
                "good.example.com": FakeResponse(
                    200,
                    {"Content-Type": "application/rss+xml"},
                    rss_with_link("v1", "Victim", "https://good.example.com/1"),
                ),
            }
        )
        victim.refresh_from_db()
        self.assertIsNotNone(victim.last_checked)
        self.assertEqual(
            Article.objects.get(title="Evil").text_content, "summary of Evil"
        )

    def test_bad_charset_entry_page_does_not_stop_older_feed(self):
        victim = self._follow(self.user, self.feed, "https://good.example.com/rss")
        self._follow(
            self.attacker,
            self.attacker_feed,
            "https://evil.example.com/rss",
            fetch_full_text=True,
        )
        self._run(
            {
                "evil.example.com": [
                    FakeResponse(
                        200,
                        {"Content-Type": "application/rss+xml"},
                        rss_with_link("e1", "Evil", "https://evil.example.com/p"),
                    ),
                    FakeResponse(
                        200, {"Content-Type": "text/html; charset=idna"}, b"<p>x</p>"
                    ),
                ],
                "good.example.com": FakeResponse(
                    200,
                    {"Content-Type": "application/rss+xml"},
                    rss_with_link("v1", "Victim", "https://good.example.com/1"),
                ),
            }
        )
        victim.refresh_from_db()
        self.assertIsNotNone(victim.last_checked)

    def test_relative_entry_link_resolved_against_final_url(self):
        self._follow(self.user, self.feed, "https://feeds.example.com/rss")
        self._run(
            {
                "feeds.example.com": FakeResponse(
                    301, {"Location": "https://cdn.example.net/feed.xml"}
                ),
                "cdn.example.net": FakeResponse(
                    200, {"Content-Type": "application/atom+xml"}, ATOM_RELATIVE
                ),
            }
        )
        self.assertEqual(
            Article.objects.get().source_url, "https://cdn.example.net/posts/a"
        )

    def test_compressed_feed_refused_and_logged(self):
        followed = self._follow(self.user, self.feed, "https://feeds.example.com/rss")
        with self.assertLogs("text_to_audio.tasks", level="WARNING") as logs:
            self._run(
                {
                    "feeds.example.com": FakeResponse(
                        200,
                        {
                            "Content-Type": "application/rss+xml",
                            "Content-Encoding": "gzip",
                        },
                        gzip.compress(RSS),
                    )
                }
            )
        self.assertTrue(any("[FEED-FETCH-ENCODING]" in line for line in logs.output))
        followed.refresh_from_db()
        self.assertIsNone(followed.last_checked)
        self.assertFalse(Article.objects.exists())


class ValidatorPortPolicyTests(NetworkTripwire):
    """The submit-time validator refuses the ports the fetch refuses (80/443 only)."""

    def test_non_default_port_rejected(self):
        from text_to_audio.validators import validate_url_not_ssrf

        for url in (
            "https://example.com:8443/a",
            "http://example.com:8080/a",
            "http://example.com:443/a",
            "https://93.184.216.34:8443/a",
        ):
            with self.subTest(url=url), patch(
                "socket.getaddrinfo", fake_getaddrinfo({})
            ):
                with self.assertRaises(ValidationError):
                    validate_url_not_ssrf(url)

    def test_default_ports_accepted(self):
        from text_to_audio.validators import validate_url_not_ssrf

        for url in (
            "https://example.com:443/a",
            "http://example.com:80/a",
            "https://example.com/a",
        ):
            with self.subTest(url=url), patch(
                "socket.getaddrinfo", fake_getaddrinfo({})
            ):
                validate_url_not_ssrf(url)


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
