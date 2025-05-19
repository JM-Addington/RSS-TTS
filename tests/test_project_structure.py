"""Tests for the project structure."""
import os
import unittest


class TestProjectStructure(unittest.TestCase):
    """Test class for validating the basic project structure."""

    def test_manage_py_exists(self):
        """Ensure manage.py file exists at the project root."""
        self.assertTrue(os.path.isfile("manage.py"))

    def test_settings_exists(self):
        """Ensure settings.py file exists in the rss_tts directory."""
        self.assertTrue(os.path.isfile(os.path.join("rss_tts", "settings.py")))


if __name__ == "__main__":
    unittest.main()
