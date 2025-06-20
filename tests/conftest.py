"""Pytest configuration file for the text_to_audio app."""

import os
import sys
from types import SimpleNamespace

import django
import openai

from tests.helpers import make_chat_completion

# Add the project root directory to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Setup Django settings


def pytest_configure():
    """Configure Django for pytest."""
    # If DJANGO_SETTINGS_MODULE is not set, use the project's settings
    if not os.environ.get("DJANGO_SETTINGS_MODULE"):
        os.environ["DJANGO_SETTINGS_MODULE"] = "rss_tts.settings"

        # Set a dummy secret key for testing
        os.environ["DJANGO_SECRET_KEY"] = "test-secret-key"

        # Set Django debug mode
        os.environ["DJANGO_DEBUG"] = "True"

    django.setup()


# Provide default patched OpenAI chat completion so stray calls return valid structure

import pytest  # noqa: E402  # pylint: disable=wrong-import-position


@pytest.fixture(autouse=True)
def patch_openai(monkeypatch):
    """Autouse fixture to patch openai chat completion create methods."""

    def _fake_create(*args, **kwargs):  # noqa: D401
        # Return dummy successful structured response
        return make_chat_completion()

    # Patch both style entry points: module-level and client-level
    monkeypatch.setattr(openai.ChatCompletion, "create", _fake_create, raising=False)
    try:
        client = openai.OpenAI()
        monkeypatch.setattr(
            client.chat.completions, "create", _fake_create, raising=False
        )
    except Exception:
        pass

    yield
