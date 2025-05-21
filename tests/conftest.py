"""
Pytest configuration file for the text_to_audio app.
"""

import os
import sys

import django
from django.conf import settings

# Add the project root directory to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Setup Django settings


def pytest_configure():
    # If DJANGO_SETTINGS_MODULE is not set, use the project's settings
    if not os.environ.get("DJANGO_SETTINGS_MODULE"):
        os.environ["DJANGO_SETTINGS_MODULE"] = "rss_tts.settings"

        # Set a dummy secret key for testing
        os.environ["DJANGO_SECRET_KEY"] = "test-secret-key"

        # Set Django debug mode
        os.environ["DJANGO_DEBUG"] = "True"

    django.setup()
