"""Tests for SSRF URL validation.

Covers blocked IP ranges, blocked schemes, DNS rebinding, hostname blocks,
valid URLs, edge cases like decimal IPs and IPv4-mapped IPv6, and
redirect-based SSRF bypass prevention.
"""

import socket
from unittest.mock import MagicMock, patch

import requests

from django.core.exceptions import ValidationError
from django.test import TestCase


class TestSSRFValidatorBlockedIPs(TestCase):
    """Test that private/internal IP addresses are blocked."""

    def _validate(self, url):
        from text_to_audio.validators import validate_url_not_ssrf

        return validate_url_not_ssrf(url)

    def test_loopback_ipv4(self):
        with self.assertRaises(ValidationError):
            self._validate("http://127.0.0.1/path")

    def test_loopback_ipv6(self):
        with self.assertRaises(ValidationError):
            self._validate("http://[::1]/path")

    def test_private_10_network(self):
        with self.assertRaises(ValidationError):
            self._validate("http://10.0.0.1/path")

    def test_private_172_network(self):
        with self.assertRaises(ValidationError):
            self._validate("http://172.16.0.5/path")

    def test_private_192_network(self):
        with self.assertRaises(ValidationError):
            self._validate("http://192.168.1.1/path")

    def test_aws_metadata_endpoint(self):
        with self.assertRaises(ValidationError):
            self._validate("http://169.254.169.254/latest/meta-data/")

    def test_gcp_metadata_hostname(self):
        with self.assertRaises(ValidationError):
            self._validate("http://metadata.google.internal/")

    def test_alibaba_metadata(self):
        with self.assertRaises(ValidationError):
            self._validate("http://100.100.100.200/")

    def test_ipv6_unique_local(self):
        with self.assertRaises(ValidationError):
            self._validate("http://[fd00::1]/path")

    def test_ipv6_link_local(self):
        with self.assertRaises(ValidationError):
            self._validate("http://[fe80::1]/path")

    def test_unspecified_address(self):
        with self.assertRaises(ValidationError):
            self._validate("http://0.0.0.0/")


class TestSSRFValidatorBlockedSchemes(TestCase):
    """Test that non-HTTP(S) schemes are blocked."""

    def _validate(self, url):
        from text_to_audio.validators import validate_url_not_ssrf

        return validate_url_not_ssrf(url)

    def test_ftp_scheme(self):
        with self.assertRaises(ValidationError):
            self._validate("ftp://example.com/file")

    def test_file_scheme(self):
        with self.assertRaises(ValidationError):
            self._validate("file:///etc/passwd")

    def test_gopher_scheme(self):
        with self.assertRaises(ValidationError):
            self._validate("gopher://evil.com/")


class TestSSRFValidatorHostnameBlocks(TestCase):
    """Test that dangerous hostnames and DNS rebinding are blocked."""

    def _validate(self, url):
        from text_to_audio.validators import validate_url_not_ssrf

        return validate_url_not_ssrf(url)

    def test_localhost(self):
        with self.assertRaises(ValidationError):
            self._validate("http://localhost/path")

    def test_localhost_with_port(self):
        with self.assertRaises(ValidationError):
            self._validate("http://localhost:8080/path")

    def test_hostname_resolving_to_private_ip(self):
        """Mock DNS to return a private IP for a public-looking hostname."""
        fake_result = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.1", 80))]
        with patch("socket.getaddrinfo", return_value=fake_result):
            with self.assertRaises(ValidationError):
                self._validate("http://evil-rebind.example.com/path")


class TestSSRFValidatorValidURLs(TestCase):
    """Test that legitimate public URLs pass validation."""

    def _validate(self, url):
        from text_to_audio.validators import validate_url_not_ssrf

        return validate_url_not_ssrf(url)

    def _mock_public_dns(self):
        """Return a mock that resolves to a public IP."""
        fake_result = [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 80))
        ]
        return patch("socket.getaddrinfo", return_value=fake_result)

    def test_https_example_com(self):
        with self._mock_public_dns():
            self._validate("https://example.com/article")

    def test_https_nytimes(self):
        with self._mock_public_dns():
            self._validate("https://www.nytimes.com/2024/01/01/article.html")

    def test_http_blog(self):
        with self._mock_public_dns():
            self._validate("http://blog.example.org/post/123")


class TestSSRFValidatorEdgeCases(TestCase):
    """Test edge cases: auth info, decimal IPs, ports, IPv4-mapped IPv6."""

    def _validate(self, url):
        from text_to_audio.validators import validate_url_not_ssrf

        return validate_url_not_ssrf(url)

    def test_url_with_auth_info(self):
        """URLs with user:pass@ targeting internal hosts should be blocked."""
        with self.assertRaises(ValidationError):
            self._validate("http://user:pass@127.0.0.1/")

    def test_decimal_ip_encoding(self):
        """127.0.0.1 encoded as decimal integer 2130706433."""
        with self.assertRaises(ValidationError):
            self._validate("http://2130706433/")

    def test_loopback_with_port(self):
        with self.assertRaises(ValidationError):
            self._validate("http://127.0.0.1:8080/")

    def test_ipv4_mapped_ipv6(self):
        with self.assertRaises(ValidationError):
            self._validate("http://[::ffff:127.0.0.1]/")


class TestFormSSRFValidation(TestCase):
    """Test that ArticleSubmissionForm rejects SSRF URLs at the form validation layer.

    AIDEV-NOTE: Ensures form-level SSRF check catches bad URLs before object creation (#190)
    """

    def _build_form_data(self, source_url):
        """Build minimal form data with a source_url."""
        return {
            "source_url": source_url,
            "text_content": "",
            "title": "",
            "tts_provider": "",
            "voice_id": "",
            "speed": "",
            "voice_preset": "",
        }

    def _make_form(self, source_url):
        from text_to_audio.forms import ArticleSubmissionForm

        return ArticleSubmissionForm(data=self._build_form_data(source_url), user=None)

    def test_form_rejects_ssrf_url(self):
        """AWS metadata endpoint should be rejected at form validation."""
        form = self._make_form("http://169.254.169.254/latest/meta-data/")
        self.assertFalse(form.is_valid())
        self.assertIn("source_url", form.errors)

    def test_form_rejects_localhost_url(self):
        """Localhost URLs should be rejected at form validation."""
        form = self._make_form("http://localhost/path")
        self.assertFalse(form.is_valid())
        self.assertIn("source_url", form.errors)

    def test_form_rejects_private_ip(self):
        """Private IP URLs should be rejected at form validation."""
        form = self._make_form("http://10.0.0.1/secret")
        self.assertFalse(form.is_valid())
        self.assertIn("source_url", form.errors)

    def test_form_accepts_public_url(self):
        """Public URLs should pass SSRF validation (may fail on other fields)."""
        fake_result = [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 80))
        ]
        with patch("socket.getaddrinfo", return_value=fake_result):
            form = self._make_form("https://example.com/article")
            # Form may be invalid for other reasons (model fields), but
            # source_url should NOT have SSRF errors
            form.is_valid()
            source_url_errors = form.errors.get("source_url", [])
            ssrf_errors = [
                e
                for e in source_url_errors
                if "private" in str(e).lower()
                or "internal" in str(e).lower()
                or "not allowed" in str(e).lower()
            ]
            self.assertEqual(ssrf_errors, [])


class TestSSRFRedirectBypass(TestCase):
    """Test that redirect-based SSRF bypass is blocked in fetch_url_content.

    AIDEV-NOTE: Validates redirect following validates each hop with SSRF check (#190)
    """

    PUBLIC_DNS = [
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 80))
    ]

    def _make_redirect_response(self, location, status_code=302):
        """Create a mock response that represents a redirect."""
        resp = MagicMock(spec=requests.Response)
        resp.status_code = status_code
        resp.headers = {"Location": location}
        resp.is_redirect = True
        resp.text = ""
        return resp

    def _make_ok_response(self, content="<html>OK</html>"):
        """Create a mock 200 OK response."""
        resp = MagicMock(spec=requests.Response)
        resp.status_code = 200
        resp.headers = {}
        resp.is_redirect = False
        resp.text = content
        return resp

    @patch("socket.getaddrinfo")
    @patch("text_to_audio.utils.requests.get")
    def test_redirect_to_private_ip_blocked(self, mock_get, mock_dns):
        """Public URL redirecting to 127.0.0.1 should be blocked."""
        from text_to_audio.utils import fetch_url_content

        mock_dns.return_value = self.PUBLIC_DNS
        # First request returns a redirect to a private IP
        mock_get.return_value = self._make_redirect_response(
            "http://127.0.0.1/secret"
        )

        success, content, error = fetch_url_content(
            "https://example.com/article", max_retries=1
        )
        self.assertFalse(success)
        self.assertIn("blocked", error.lower())

    @patch("socket.getaddrinfo")
    @patch("text_to_audio.utils.requests.get")
    def test_redirect_to_metadata_endpoint_blocked(self, mock_get, mock_dns):
        """Public URL redirecting to cloud metadata endpoint should be blocked."""
        from text_to_audio.utils import fetch_url_content

        mock_dns.return_value = self.PUBLIC_DNS
        mock_get.return_value = self._make_redirect_response(
            "http://169.254.169.254/latest/meta-data/"
        )

        success, content, error = fetch_url_content(
            "https://example.com/article", max_retries=1
        )
        self.assertFalse(success)
        self.assertIn("blocked", error.lower())

    @patch("socket.getaddrinfo")
    @patch("text_to_audio.utils.requests.get")
    def test_redirect_to_public_url_allowed(self, mock_get, mock_dns):
        """Public URL redirecting to another public URL should work."""
        from text_to_audio.utils import fetch_url_content

        mock_dns.return_value = self.PUBLIC_DNS
        # First call: redirect; second call: OK
        mock_get.side_effect = [
            self._make_redirect_response("https://cdn.example.com/article"),
            self._make_ok_response("<html>Article content</html>"),
        ]

        success, content, error = fetch_url_content(
            "https://example.com/article", max_retries=1
        )
        self.assertTrue(success)
        self.assertEqual(content, "<html>Article content</html>")

    @patch("socket.getaddrinfo")
    @patch("text_to_audio.utils.requests.get")
    def test_multiple_redirects_to_private_ip_blocked(self, mock_get, mock_dns):
        """Chain of redirects ending at private IP should be blocked."""
        from text_to_audio.utils import fetch_url_content

        mock_dns.return_value = self.PUBLIC_DNS
        # Two public redirects, then a redirect to private IP
        mock_get.side_effect = [
            self._make_redirect_response("https://cdn1.example.com/"),
            self._make_redirect_response("https://cdn2.example.com/"),
            self._make_redirect_response("http://10.0.0.1/internal"),
        ]

        success, content, error = fetch_url_content(
            "https://example.com/article", max_retries=1
        )
        self.assertFalse(success)
        self.assertIn("blocked", error.lower())

    @patch("socket.getaddrinfo")
    @patch("text_to_audio.utils.requests.get")
    def test_too_many_redirects_blocked(self, mock_get, mock_dns):
        """Exceeding max redirect depth should be blocked."""
        from text_to_audio.utils import fetch_url_content

        mock_dns.return_value = self.PUBLIC_DNS
        # 11 redirects (exceeds limit of 10)
        mock_get.side_effect = [
            self._make_redirect_response(f"https://hop{i}.example.com/")
            for i in range(11)
        ]

        success, content, error = fetch_url_content(
            "https://example.com/article", max_retries=1
        )
        self.assertFalse(success)
        self.assertIn("redirect", error.lower())
