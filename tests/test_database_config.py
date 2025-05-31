"""Test flexible database configuration."""

import os
from unittest import mock

from django.test import TestCase


class DatabaseConfigurationTest(TestCase):
    """Test database configuration with different environment variables."""

    def test_default_sqlite_configuration(self):
        """Test that SQLite is used by default when no env vars are set."""
        # Import settings fresh with no database env vars
        with mock.patch.dict(os.environ, {}, clear=True):
            # Remove any existing database env vars
            for key in list(os.environ.keys()):
                if key.startswith(("DATABASE_URL", "POSTGRES_")):
                    del os.environ[key]

            # Re-import settings to get fresh configuration
            from importlib import reload

            import rss_tts.settings as settings

            reload(settings)

            # Check that SQLite is configured
            self.assertEqual(
                settings.DATABASES["default"]["ENGINE"], "django.db.backends.sqlite3"
            )
            self.assertIn("db.sqlite3", str(settings.DATABASES["default"]["NAME"]))

    def test_database_url_configuration(self):
        """Test that DATABASE_URL is used when provided."""
        test_db_url = "postgresql://testuser:testpass@testhost:5432/testdb"

        with mock.patch.dict(os.environ, {"DATABASE_URL": test_db_url}):
            # Re-import settings to get fresh configuration
            from importlib import reload

            import rss_tts.settings as settings

            reload(settings)

            # Check that PostgreSQL is configured
            db_config = settings.DATABASES["default"]
            self.assertEqual(db_config["ENGINE"], "django.db.backends.postgresql")
            self.assertEqual(db_config["NAME"], "testdb")
            self.assertEqual(db_config["USER"], "testuser")
            self.assertEqual(db_config["PASSWORD"], "testpass")
            self.assertEqual(db_config["HOST"], "testhost")
            self.assertEqual(db_config["PORT"], 5432)

    def test_explicit_postgres_configuration(self):
        """Test that explicit PostgreSQL env vars work."""
        postgres_env = {
            "POSTGRES_DB": "mydb",
            "POSTGRES_USER": "myuser",
            "POSTGRES_PASSWORD": "mypass",
            "POSTGRES_HOST": "myhost",
            "POSTGRES_PORT": "5433",
        }

        # Clear DATABASE_URL to ensure it doesn't take precedence
        with mock.patch.dict(os.environ, postgres_env):
            if "DATABASE_URL" in os.environ:
                del os.environ["DATABASE_URL"]

            # Re-import settings to get fresh configuration
            from importlib import reload

            import rss_tts.settings as settings

            reload(settings)

            # Check that PostgreSQL is configured with explicit values
            db_config = settings.DATABASES["default"]
            self.assertEqual(db_config["ENGINE"], "django.db.backends.postgresql")
            self.assertEqual(db_config["NAME"], "mydb")
            self.assertEqual(db_config["USER"], "myuser")
            self.assertEqual(db_config["PASSWORD"], "mypass")
            self.assertEqual(db_config["HOST"], "myhost")
            self.assertEqual(db_config["PORT"], "5433")

    def test_database_url_takes_precedence(self):
        """Test that DATABASE_URL takes precedence over explicit vars."""
        test_db_url = "postgresql://urluser:urlpass@urlhost:5432/urldb"
        postgres_env = {
            "DATABASE_URL": test_db_url,
            "POSTGRES_DB": "ignored_db",
            "POSTGRES_USER": "ignored_user",
            "POSTGRES_PASSWORD": "ignored_pass",
            "POSTGRES_HOST": "ignored_host",
        }

        with mock.patch.dict(os.environ, postgres_env):
            # Re-import settings to get fresh configuration
            from importlib import reload

            import rss_tts.settings as settings

            reload(settings)

            # Check that DATABASE_URL config is used
            db_config = settings.DATABASES["default"]
            self.assertEqual(db_config["NAME"], "urldb")
            self.assertEqual(db_config["USER"], "urluser")
            self.assertEqual(db_config["HOST"], "urlhost")
