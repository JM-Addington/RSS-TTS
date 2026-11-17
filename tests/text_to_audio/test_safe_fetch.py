"""Unit tests for text_to_audio.safe_fetch, the pinned SSRF-safe fetch (#190).

No DNS and no network: every test injects ``resolver=`` and ``connector=`` fakes that record
their calls, so a refusal can be shown to happen BEFORE any connect (or any resolve).

AIDEV-NOTE: each class names the mutant it pins (M-HOP, M-PIN, M-ALLIPS, M-CAP, M-NUMHOST);
a mutant that leaves every cell here green means the guard is untested -- do not weaken these.
"""

import unittest
from unittest.mock import patch

from text_to_audio import safe_fetch
from text_to_audio.safe_fetch import FetchRefused, fetch_url

PUBLIC_IP = "93.184.216.34"
CAP = 1024


class FakeResponse:
    """Stands in for urllib3's unread response: status, headers, stream(n)."""

    def __init__(self, status=200, headers=None, body=b"", chunk=None):
        self.status = status
        self.headers = headers or {}
        self._body = body
        self._chunk = chunk
        self.streamed = 0
        self.released = False

    def stream(self, n):
        size = self._chunk or n
        for i in range(0, len(self._body), size):
            piece = self._body[i : i + size]
            self.streamed += len(piece)
            yield piece

    def release_conn(self):
        self.released = True


class FakeConnector:
    """Records every connect; answers from a list of responses in order."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def __call__(self, **kwargs):
        self.calls.append(kwargs)
        if not self.responses:
            raise AssertionError("connector called more times than expected")
        return self.responses.pop(0)


class FakeResolver:
    """Maps host -> list of addresses; records every lookup."""

    def __init__(self, table=None):
        self.table = table or {}
        self.calls = []

    def __call__(self, host):
        self.calls.append(host)
        return self.table.get(host, [PUBLIC_IP])


def ok(body=b"<html>ok</html>", **headers):
    hdrs = {"Content-Type": "text/html; charset=utf-8"}
    hdrs.update(headers)
    return FakeResponse(200, hdrs, body)


def redirect(location, status=302):
    return FakeResponse(status, {"Location": location})


class RefusalHelper(unittest.TestCase):
    def assertRefused(self, url, code, resolver=None, connector=None):
        resolver = resolver or FakeResolver()
        connector = connector or FakeConnector(ok())
        with self.assertRaises(FetchRefused) as ctx:
            fetch_url(
                url,
                ports={"http": 80, "https": 443},
                cap=CAP,
                resolver=resolver,
                connector=connector,
            )
        self.assertEqual(ctx.exception.code, code, f"{url}: {ctx.exception.code}")
        return ctx.exception, resolver, connector


class PrivateAddressTests(RefusalHelper):
    """Literal and resolved private addresses refuse BEFORE any connect."""

    def test_literal_private_addresses_refused(self):
        for url in (
            "http://127.0.0.1/",
            "http://169.254.169.254/latest/meta-data/",
            "http://[::1]/",
            "http://[::ffff:127.0.0.1]/",
            "http://10.0.0.1/",
            "http://172.16.0.1/",
            "http://192.168.1.1/",
            "http://100.64.0.1/",
        ):
            with self.subTest(url=url):
                _, _, connector = self.assertRefused(url, safe_fetch.ADDRESS_REFUSED)
                self.assertEqual(connector.calls, [])

    def test_localhost_resolving_to_loopback_refused(self):
        resolver = FakeResolver({"localhost": ["127.0.0.1"]})
        exc, _, connector = self.assertRefused(
            "http://localhost/", safe_fetch.ADDRESS_REFUSED, resolver=resolver
        )
        self.assertEqual(connector.calls, [])
        self.assertEqual(exc.host, "localhost")


class AllAddressesTests(RefusalHelper):
    """M-ALLIPS: one private record among public ones refuses the whole name."""

    def test_one_private_address_refuses_name(self):
        resolver = FakeResolver({"mixed.example": [PUBLIC_IP, "10.0.0.1"]})
        _, _, connector = self.assertRefused(
            "http://mixed.example/", safe_fetch.ADDRESS_REFUSED, resolver=resolver
        )
        self.assertEqual(connector.calls, [])


class NumericHostTests(RefusalHelper):
    """M-NUMHOST: numeric spellings never reach the resolver."""

    def test_numeric_hosts_refused_without_resolve(self):
        for url in (
            "http://2130706433/",
            "http://0177.0.0.1/",
            "http://0x7f.0.0.1/",
            "http://127.1/",
        ):
            with self.subTest(url=url):
                _, resolver, connector = self.assertRefused(url, safe_fetch.URL_HOST)
                self.assertEqual(resolver.calls, [])
                self.assertEqual(connector.calls, [])

    def test_hex_looking_name_is_not_numeric(self):
        self.assertFalse(safe_fetch.numeric_host("0xdeadbeef.com"))


class SchemePortUserinfoTests(RefusalHelper):
    def test_bad_schemes_refused(self):
        for url in ("file:///etc/passwd", "gopher://x/", "ftp://x/"):
            with self.subTest(url=url):
                _, _, connector = self.assertRefused(url, safe_fetch.URL_SCHEME)
                self.assertEqual(connector.calls, [])

    def test_userinfo_refused(self):
        _, resolver, connector = self.assertRefused(
            "http://user:pw@example.com/", safe_fetch.URL_HOST
        )
        self.assertEqual(resolver.calls, [])
        self.assertEqual(connector.calls, [])

    def test_non_default_port_refused(self):
        _, _, connector = self.assertRefused(
            "http://example.com:8080/", safe_fetch.URL_PORT
        )
        self.assertEqual(connector.calls, [])

    def test_default_ports_policy_is_http_and_https(self):
        self.assertEqual(safe_fetch.DEFAULT_PORTS, {"http": 80, "https": 443})


class RedirectTests(RefusalHelper):
    """M-HOP: every Location goes back through the full check."""

    def test_redirect_to_metadata_refused_after_one_connect(self):
        for location in ("http://169.254.169.254/", "http://127.0.0.1/"):
            with self.subTest(location=location):
                connector = FakeConnector(redirect(location), ok())
                self.assertRefused(
                    "http://example.com/",
                    safe_fetch.ADDRESS_REFUSED,
                    connector=connector,
                )
                self.assertEqual(len(connector.calls), 1)
                self.assertEqual(connector.calls[0]["ip"], PUBLIC_IP)

    def test_redirect_to_name_resolving_private_refused(self):
        resolver = FakeResolver({"internal.example": ["10.1.2.3"]})
        connector = FakeConnector(redirect("http://internal.example/x"), ok())
        self.assertRefused(
            "http://example.com/",
            safe_fetch.ADDRESS_REFUSED,
            resolver=resolver,
            connector=connector,
        )
        self.assertEqual(len(connector.calls), 1)

    def test_redirect_to_file_scheme_refused(self):
        connector = FakeConnector(redirect("file:///etc/passwd"), ok())
        self.assertRefused(
            "http://example.com/", safe_fetch.URL_SCHEME, connector=connector
        )
        self.assertEqual(len(connector.calls), 1)

    def test_redirect_chain_over_limit_refused(self):
        connector = FakeConnector(
            redirect("/1"), redirect("/2"), redirect("/3"), redirect("/4"), ok()
        )
        self.assertRefused(
            "http://example.com/", safe_fetch.REDIRECT_LIMIT, connector=connector
        )
        self.assertEqual(len(connector.calls), 4)

    def test_three_redirects_allowed(self):
        connector = FakeConnector(
            redirect("/1"), redirect("https://www.example.com/2"), redirect("/3"), ok()
        )
        result = fetch_url(
            "http://example.com/",
            cap=CAP,
            resolver=FakeResolver(),
            connector=connector,
        )
        self.assertEqual(result.redirects, 3)
        self.assertEqual(result.host, "example.com")
        self.assertEqual(result.final_host, "www.example.com")
        self.assertEqual(connector.calls[-1]["path"], "/3")


class PinningTests(unittest.TestCase):
    """M-PIN: the connector is handed the VALIDATED ip, never the name to re-resolve."""

    def test_connector_receives_validated_ip_and_name(self):
        resolver = FakeResolver({"example.com": [PUBLIC_IP]})
        connector = FakeConnector(ok())
        fetch_url(
            "https://example.com/a?b=1",
            cap=CAP,
            resolver=resolver,
            connector=connector,
        )
        call = connector.calls[0]
        self.assertEqual(call["ip"], PUBLIC_IP)
        self.assertNotEqual(call["ip"], "example.com")
        self.assertEqual(call["host"], "example.com")
        self.assertEqual(call["path"], "/a?b=1")
        self.assertEqual(resolver.calls, ["example.com"])

    def test_one_resolve_per_hop(self):
        resolver = FakeResolver()
        connector = FakeConnector(redirect("https://b.example/"), ok())
        fetch_url("https://a.example/", cap=CAP, resolver=resolver, connector=connector)
        self.assertEqual(resolver.calls, ["a.example", "b.example"])

    def test_pool_kwargs_pin_ip_and_check_cert_against_name(self):
        kwargs = safe_fetch.pinned_pool_kwargs(
            "https", ip=PUBLIC_IP, host="example.com", timeout=5
        )
        self.assertEqual(kwargs["host"], PUBLIC_IP)
        self.assertEqual(kwargs["server_hostname"], "example.com")
        self.assertEqual(kwargs["assert_hostname"], "example.com")
        self.assertEqual(kwargs["cert_reqs"], "CERT_REQUIRED")
        http_kwargs = safe_fetch.pinned_pool_kwargs(
            "http", ip=PUBLIC_IP, host="example.com", timeout=5
        )
        self.assertEqual(http_kwargs["host"], PUBLIC_IP)
        self.assertEqual(http_kwargs["port"], 80)

    def test_installed_urllib3_accepts_pinned_kwargs(self):
        """The real pool class takes the kwargs and keeps the IP as its host (no connect made)."""
        import urllib3

        kwargs = safe_fetch.pinned_pool_kwargs(
            "https", ip=PUBLIC_IP, host="example.com", timeout=5
        )
        pool = urllib3.HTTPSConnectionPool(**kwargs)
        conn = pool._new_conn()  # builds the connection object; does not connect
        self.assertEqual(conn.host, PUBLIC_IP)
        self.assertEqual(conn.server_hostname, "example.com")
        self.assertEqual(conn.assert_hostname, "example.com")
        pool.close()

    def test_connect_pinned_builds_pool_at_ip_and_sends_host_header(self):
        """The default connector: pool at the IP, Host = name, no redirect, no decode."""
        import urllib3

        seen: dict = {}

        class FakePool:
            ConnectionCls = urllib3.connection.HTTPSConnection

            def __init__(self, **kwargs):
                seen["pool"] = kwargs

            def urlopen(self, method, path, **kwargs):
                seen["urlopen"] = (method, path, kwargs)
                return FakeResponse(200)

        for scheme, attr in (
            ("https", "HTTPSConnectionPool"),
            ("http", "HTTPConnectionPool"),
        ):
            with self.subTest(scheme=scheme), patch.object(urllib3, attr, FakePool):
                response = safe_fetch.connect_pinned(
                    ip=PUBLIC_IP,
                    host="example.com",
                    path="/p",
                    timeout=5,
                    scheme=scheme,
                )
                safe_fetch.release(response)
                self.assertEqual(seen["pool"]["host"], PUBLIC_IP)
                method, path, kwargs = seen["urlopen"]
                self.assertEqual((method, path), ("GET", "/p"))
                self.assertEqual(kwargs["headers"]["Host"], "example.com")
                self.assertEqual(kwargs["headers"]["Accept-Encoding"], "identity")
                self.assertIs(kwargs["redirect"], False)
                self.assertIs(kwargs["decode_content"], False)
                self.assertIs(kwargs["preload_content"], False)


class SizeCapTests(RefusalHelper):
    """M-CAP: running count AND Content-Length are both enforced."""

    def test_body_over_cap_without_content_length_refused(self):
        response = FakeResponse(200, {}, b"x" * (CAP + 1), chunk=100)
        self.assertRefused(
            "http://example.com/",
            safe_fetch.TOO_LARGE,
            connector=FakeConnector(response),
        )
        self.assertLessEqual(response.streamed, CAP + 100)
        self.assertTrue(response.released)

    def test_content_length_over_cap_refused_before_body(self):
        response = FakeResponse(200, {"Content-Length": str(CAP + 1)}, b"x")
        self.assertRefused(
            "http://example.com/",
            safe_fetch.TOO_LARGE,
            connector=FakeConnector(response),
        )
        self.assertEqual(response.streamed, 0)

    def test_body_exactly_at_cap_allowed(self):
        response = FakeResponse(200, {}, b"x" * CAP, chunk=100)
        result = fetch_url(
            "http://example.com/",
            cap=CAP,
            resolver=FakeResolver(),
            connector=FakeConnector(response),
        )
        self.assertEqual(len(result.data), CAP)


class StatusAndHappyPathTests(RefusalHelper):
    def test_happy_path(self):
        connector = FakeConnector(ok(b"<html>hi</html>"))
        result = fetch_url(
            "http://example.com/",
            cap=CAP,
            accept="text/html",
            resolver=FakeResolver(),
            connector=connector,
        )
        self.assertEqual(result.data, b"<html>hi</html>")
        self.assertEqual(result.status, 200)
        self.assertEqual(result.host, "example.com")
        self.assertEqual(result.final_host, "example.com")
        self.assertEqual(result.redirects, 0)
        self.assertEqual(result.content_type, "text/html; charset=utf-8")
        self.assertEqual(connector.calls[0]["accept"], "text/html")
        self.assertEqual(connector.calls[0]["scheme"], "http")

    def test_non_200_carries_status(self):
        for status in (403, 404, 500):
            with self.subTest(status=status):
                exc, _, _ = self.assertRefused(
                    "http://example.com/",
                    safe_fetch.HTTP_STATUS,
                    connector=FakeConnector(FakeResponse(status)),
                )
                self.assertEqual(exc.status, status)

    def test_connector_error_becomes_connect_failed(self):
        def boom(**kwargs):
            raise OSError("refused")

        self.assertRefused(
            "http://example.com/", safe_fetch.CONNECT_FAILED, connector=boom
        )

    def test_resolver_failure_is_dns_failed(self):
        import socket

        def fail(host):
            raise socket.gaierror("nope")

        self.assertRefused("http://nx.example/", safe_fetch.DNS_FAILED, resolver=fail)

    def test_deadline_passed_is_timeout(self):
        ticks = iter([0.0, 100.0, 100.0, 100.0])
        with self.assertRaises(FetchRefused) as ctx:
            fetch_url(
                "http://example.com/",
                cap=CAP,
                total_timeout=15,
                resolver=FakeResolver(),
                connector=FakeConnector(ok()),
                clock=lambda: next(ticks),
            )
        self.assertEqual(ctx.exception.code, safe_fetch.TIMEOUT)


class AddressAllowedTests(unittest.TestCase):
    def test_tunnel_and_odd_ranges_refused(self):
        for raw in (
            "64:ff9b::a00:1",  # NAT64 of 10.0.0.1
            "2001:0:4136:e378:8000:63bf:3fff:fdd2",  # Teredo
            "2002:7f00:1::",  # 6to4 of 127.0.0.1
            "fec0::1",  # site-local
            "192.88.99.1",  # 6to4 relay anycast
            "0.0.0.0",
            "224.0.0.1",
            "not-an-ip",
        ):
            with self.subTest(raw=raw):
                self.assertFalse(safe_fetch.address_allowed(raw))

    def test_public_allowed(self):
        self.assertTrue(safe_fetch.address_allowed(PUBLIC_IP))
        self.assertTrue(
            safe_fetch.address_allowed("2606:2800:220:1:248:1893:25c8:1946")
        )
