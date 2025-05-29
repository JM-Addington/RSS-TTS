#!/usr/bin/env python
"""Specific test runner for multi-voice functionality."""

import os
import sys
import unittest
from unittest.mock import MagicMock, patch

# Set up the test environment
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "rss_tts.settings")

# Import Django and configure settings
import django
django.setup()

from django.conf import settings
# Set TESTING flag
settings.TESTING = True

# Create mock modules for audio dependencies
class MockAudioSegment:
    """Mock AudioSegment for testing."""

    @classmethod
    def empty(cls):
        """Return empty mock."""
        return cls()

    @classmethod
    def from_mp3(cls, file_path):
        """Mock mp3 loading."""
        return cls()

    @property
    def duration_seconds(self):
        """Mock duration property."""
        return 30

    def __add__(self, other):
        """Mock addition."""
        return self

    def set_frame_rate(self, rate):
        """Mock frame rate setting."""
        return self

    def export(self, path, format=None, bitrate=None, tags=None, parameters=None):
        """Mock export."""
        with open(path, "w") as f:
            f.write("mock audio data")

# Create mock for pydub module
mock_pydub = MagicMock()
mock_pydub.AudioSegment = MockAudioSegment

# Create mock for audioop module
mock_audioop = MagicMock()

# Add mocks to sys.modules
sys.modules["pydub"] = mock_pydub
sys.modules["pydub.audio_segment"] = MagicMock()
sys.modules["pydub.utils"] = MagicMock()
sys.modules["audioop"] = mock_audioop
sys.modules["pyaudioop"] = mock_audioop

# Now import the test class we want to run
from tests.text_to_audio.test_multi_voice import MultiVoiceValidationTest

if __name__ == "__main__":
    # Run only the MultiVoiceValidationTest test case
    unittest.TextTestRunner(verbosity=2).run(
        unittest.TestLoader().loadTestsFromTestCase(MultiVoiceValidationTest)
    )
