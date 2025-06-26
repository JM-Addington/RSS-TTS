"""Test configuration with mocks for audio dependencies."""

# Add the project to the Python path
import os
import sys
from unittest.mock import MagicMock

import django
from django.conf import settings

# Set up Django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "rss_tts.settings")
django.setup()

# Set TESTING flag
settings.TESTING = True

# Create mock modules for pydub


class MockAudioSegment:
    """Mock AudioSegment for testing."""

    def __init__(self):
        self.duration_seconds = 10.0  # Default duration for testing

    @classmethod
    def empty(cls):
        """Return empty mock."""
        return cls()

    @classmethod
    def from_mp3(cls, file_path):
        """Mock mp3 loading."""
        return cls()

    @classmethod
    def silent(cls, duration=0):
        """Return a silent MockAudioSegment of given duration (ms)."""
        segment = cls()
        segment.duration_seconds = duration / 1000 if duration else 0
        return segment

    def __add__(self, other):
        """Mock addition."""
        return self

    def __iadd__(self, other):
        """Mock in-place addition."""
        return self

    def set_frame_rate(self, rate):
        """Mock frame rate setting."""
        return self

    def export(self, path, format=None, bitrate=None, tags=None, parameters=None):
        """Mock export."""
        # Ensure parent directory exists
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            f.write(b"mock audio data")


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

# Now we can import the rest of the code
