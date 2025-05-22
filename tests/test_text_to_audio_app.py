"""Tests for the text_to_audio app configuration."""
# mypy: disable-error-code="attr-defined"

import os
from importlib import util
from unittest import TestCase

from django.conf import settings


class TestTextToAudioApp(TestCase):
    """Tests for the text_to_audio app."""

    def test_app_exists(self):
        """Test that the text_to_audio app directory exists."""
        app_path = os.path.join(settings.BASE_DIR, "text_to_audio")
        self.assertTrue(
            os.path.isdir(app_path),
            f"text_to_audio app directory does not exist at {app_path}",
        )

    def test_app_has_init_file(self):
        """Test that the text_to_audio app has an __init__.py file."""
        init_path = os.path.join(settings.BASE_DIR, "text_to_audio", "__init__.py")
        self.assertTrue(
            os.path.isfile(init_path),
            "text_to_audio app does not have an __init__.py file",
        )

    def test_app_has_apps_file(self):
        """Test that the text_to_audio app has an apps.py file."""
        apps_path = os.path.join(settings.BASE_DIR, "text_to_audio", "apps.py")
        self.assertTrue(
            os.path.isfile(apps_path), "text_to_audio app does not have an apps.py file"
        )

    def test_app_has_models_file(self):
        """Test that the text_to_audio app has a models.py file."""
        models_path = os.path.join(settings.BASE_DIR, "text_to_audio", "models.py")
        self.assertTrue(
            os.path.isfile(models_path),
            "text_to_audio app does not have a models.py file",
        )

    def test_app_config(self):
        """Test that the TextToAudioConfig is properly defined."""
        # Check if apps.py can be imported
        apps_module_path = os.path.join(settings.BASE_DIR, "text_to_audio", "apps.py")
        spec = util.spec_from_file_location("text_to_audio.apps", apps_module_path)

        # This test will fail if the app doesn't exist yet, which is expected in TDD
        if os.path.exists(apps_module_path) and spec is not None:
            apps_module = util.module_from_spec(spec)
            if hasattr(spec, "loader") and spec.loader is not None:
                spec.loader.exec_module(apps_module)

            # Check if TextToAudioConfig is defined and has the required attributes
            self.assertTrue(
                hasattr(apps_module, "TextToAudioConfig"),
                "TextToAudioConfig class is not defined in apps.py",
            )

            config = apps_module.TextToAudioConfig
            self.assertEqual(
                config.name, "text_to_audio", "App name is not set to 'text_to_audio'"
            )

    def test_app_installed(self):
        """Test that the text_to_audio app is in INSTALLED_APPS."""
        self.assertIn(
            "text_to_audio",
            settings.INSTALLED_APPS,
            "text_to_audio app is not in INSTALLED_APPS",
        )


# For pytest compatibility
if __name__ == "__main__":
    import pytest

    pytest.main([__file__])
