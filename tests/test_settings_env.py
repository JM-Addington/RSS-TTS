import importlib
import os
import sys
import unittest


class TestSettingsEnvironment(unittest.TestCase):
    def setUp(self):
        self.orig_env = os.environ.copy()

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self.orig_env)
        if "rss_tts.settings" in sys.modules:
            del sys.modules["rss_tts.settings"]

    def _import_settings(self):
        if "rss_tts.settings" in sys.modules:
            del sys.modules["rss_tts.settings"]
        return importlib.import_module("rss_tts.settings")

    def test_openai_key_loaded_from_env(self):
        os.environ["DJANGO_SECRET_KEY"] = "test"
        os.environ["OPENAI_API_KEY"] = "sample-key"
        settings = self._import_settings()
        self.assertEqual(settings.OPENAI_API_KEY, "sample-key")

    def test_sqlite_data_dir_from_env(self):
        os.environ["DJANGO_SECRET_KEY"] = "test"
        os.environ["SQLITE_DATA_DIR"] = "custom"
        settings = self._import_settings()
        default_db = settings.DATABASES["default"]
        self.assertEqual(default_db["ENGINE"], "django.db.backends.sqlite3")
        self.assertTrue(default_db["NAME"].endswith("custom/db.sqlite3"))
