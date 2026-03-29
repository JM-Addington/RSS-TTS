"""Tests for SSRF URL validation.

Covers blocked IP ranges, blocked schemes, DNS rebinding, hostname blocks,
valid URLs, and edge cases like decimal IPs and IPv4-mapped IPv6.
"""

import socket
from unittest.mock import patch

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
