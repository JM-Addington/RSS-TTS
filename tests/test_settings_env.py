"""Tests for Django settings environment variable loading.

This module tests that the Django settings properly load and use
environment variables for configuration.
"""

import importlib
import os
import sys
import unittest


class TestSettingsEnvironment(unittest.TestCase):
    """Test cases for environment variable handling in Django settings."""

    def setUp(self):
        """Save the original environment variables before tests."""
        self.orig_env = os.environ.copy()

    def tearDown(self):
        """Restore the original environment variables after tests.

        Also removes the settings module from sys.modules to ensure
        a fresh import in subsequent tests.
        """
        os.environ.clear()
        os.environ.update(self.orig_env)
        if "rss_tts.settings" in sys.modules:
            del sys.modules["rss_tts.settings"]

    def _import_settings(self):
        """Import the settings module with a fresh import.

        Returns:
            module: The freshly imported settings module
        """
        if "rss_tts.settings" in sys.modules:
            del sys.modules["rss_tts.settings"]
        return importlib.import_module("rss_tts.settings")

    def test_openai_key_loaded_from_env(self):
        """Test that the OpenAI API key is loaded from environment variables."""
        os.environ["DJANGO_SECRET_KEY"] = "test"
        os.environ["OPENAI_API_KEY"] = "sample-key"
        settings = self._import_settings()
        self.assertEqual(settings.OPENAI_API_KEY, "sample-key")

    def test_sqlite_data_dir_from_env(self):
        """Test that the SQLite data directory is loaded from environment variables.

        Verifies that the database engine is set to SQLite and the database path
        uses the custom directory provided in the environment variable.
        """
        os.environ["DJANGO_SECRET_KEY"] = "test"
        os.environ["SQLITE_DATA_DIR"] = "custom"
        settings = self._import_settings()
        default_db = settings.DATABASES["default"]
        self.assertEqual(default_db["ENGINE"], "django.db.backends.sqlite3")
        self.assertTrue(default_db["NAME"].endswith("custom/db.sqlite3"))

    def test_default_tts_model(self):
        """Default TTS model should be tts-1-hd when not set via env."""
        os.environ["DJANGO_SECRET_KEY"] = "test"
        settings = self._import_settings()
        self.assertEqual(settings.OPENAI_TTS_MODEL, "tts-1-hd")

    def test_tts_model_from_env(self):
        """Environment variable should override the default TTS model."""
        os.environ["DJANGO_SECRET_KEY"] = "test"
        os.environ["OPENAI_TTS_MODEL"] = "tts-1"
        settings = self._import_settings()
        self.assertEqual(settings.OPENAI_TTS_MODEL, "tts-1")

    def test_firecrawl_key_loaded_from_env(self):
        """Firecrawl API key is loaded from environment variables."""
        os.environ["DJANGO_SECRET_KEY"] = "test"
        os.environ["FIRECRAWL_API_KEY"] = "fc-key"
        settings = self._import_settings()
        self.assertEqual(settings.FIRECRAWL_API_KEY, "fc-key")

    def test_firecrawl_default_disabled(self):
        """USE_FIRECRAWL_BY_DEFAULT should be False when not set."""
        os.environ["DJANGO_SECRET_KEY"] = "test"
        settings = self._import_settings()
        self.assertFalse(settings.USE_FIRECRAWL_BY_DEFAULT)

    def test_caddy_internal_in_allowed_hosts_by_default(self):
        """caddy_internal should be in ALLOWED_HOSTS by default for Docker networking."""
        os.environ["DJANGO_SECRET_KEY"] = "test"
        settings = self._import_settings()
        self.assertIn("caddy_internal", settings.ALLOWED_HOSTS)

    def test_host_validation_allows_underscores(self):
        """Host validation regex should allow underscores for Docker container names."""
        os.environ["DJANGO_SECRET_KEY"] = "test"
        self._import_settings()
        from django.http import request as django_request

        # Test that underscored hostnames pass validation
        self.assertTrue(django_request.host_validation_re.match("caddy_internal"))
        self.assertTrue(django_request.host_validation_re.match("my_container_name"))
        self.assertTrue(django_request.host_validation_re.match("service_1:8000"))
        # Standard hostnames should still work
        self.assertTrue(django_request.host_validation_re.match("localhost"))
        self.assertTrue(django_request.host_validation_re.match("example.com"))
        self.assertTrue(django_request.host_validation_re.match("localhost:8000"))
        # IPv6 should still work
        self.assertTrue(django_request.host_validation_re.match("[::1]"))
        self.assertTrue(django_request.host_validation_re.match("[::1]:8000"))
