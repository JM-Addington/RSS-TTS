"""Test configuration with conditional mocks for audio dependencies.

This module provides conditional mocking of audio dependencies based on the
MOCK_AUDIO_DEPENDENCIES environment variable. This allows tests to run with
either real audio libraries (when available) or mocked versions.

Usage:
    # To enable audio mocking
    export MOCK_AUDIO_DEPENDENCIES=true

    # To use real audio libraries (default)
    export MOCK_AUDIO_DEPENDENCIES=false
    # or simply don't set the variable
"""

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

# Check if audio mocking is enabled
MOCK_AUDIO_DEPENDENCIES = (
    os.environ.get("MOCK_AUDIO_DEPENDENCIES", "false").lower() == "true"
)


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

    def __add__(self, other):
        """Mock addition."""
        return self

    def export(self, path, format=None, **kwargs):
        """Mock export with support for additional parameters."""
        # Create parent directory if it doesn't exist
        parent_dir = os.path.dirname(path)
        if parent_dir and not os.path.exists(parent_dir):
            os.makedirs(parent_dir, exist_ok=True)

        # Write mock audio data
        with open(path, "w") as f:
            f.write("mock audio data")

    def set_frame_rate(self, frame_rate):
        """Mock frame rate setting."""
        return self

    @property
    def duration_seconds(self):
        """Mock duration property."""
        return 60.0  # Mock 60 second duration


def apply_audio_mocks():
    """Apply audio library mocks to sys.modules."""
    print("🎭 Applying audio dependency mocks...")

    # Create mock for pydub module
    mock_pydub = MagicMock()
    mock_pydub.AudioSegment = MockAudioSegment

    # Create mock for audioop module
    mock_audioop = MagicMock()

    # Store original modules for potential restoration
    original_modules = {}
    modules_to_mock = [
        "pydub",
        "pydub.audio_segment",
        "pydub.utils",
        "audioop",
        "pyaudioop",
    ]

    for module_name in modules_to_mock:
        if module_name in sys.modules:
            original_modules[module_name] = sys.modules[module_name]

    # Apply mocks to sys.modules
    sys.modules["pydub"] = mock_pydub
    sys.modules["pydub.audio_segment"] = MagicMock()
    sys.modules["pydub.utils"] = MagicMock()
    sys.modules["audioop"] = mock_audioop
    sys.modules["pyaudioop"] = mock_audioop

    # Store original modules for potential cleanup
    if not hasattr(apply_audio_mocks, "_original_modules"):
        apply_audio_mocks._original_modules = original_modules


def remove_audio_mocks():
    """Remove audio library mocks from sys.modules."""
    print("🔄 Removing audio dependency mocks...")

    if hasattr(apply_audio_mocks, "_original_modules"):
        # Restore original modules
        for module_name, original_module in apply_audio_mocks._original_modules.items():
            sys.modules[module_name] = original_module
    else:
        # Remove mocked modules
        modules_to_remove = [
            "pydub",
            "pydub.audio_segment",
            "pydub.utils",
            "audioop",
            "pyaudioop",
        ]

        for module_name in modules_to_remove:
            if module_name in sys.modules:
                del sys.modules[module_name]


def check_audio_dependencies():
    """Check if real audio dependencies are available."""
    missing_deps = []

    try:
        import pydub  # noqa: F401
    except ImportError:
        missing_deps.append("pydub")

    try:
        import audioop  # noqa: F401
    except ImportError:
        missing_deps.append("audioop")

    return missing_deps


def pytest_configure():
    """Configure pytest with conditional audio mocking."""
    if MOCK_AUDIO_DEPENDENCIES:
        print("🎭 MOCK_AUDIO_DEPENDENCIES=true: Enabling audio mocks")
        apply_audio_mocks()
    else:
        # Check if real dependencies are available
        missing_deps = check_audio_dependencies()

        if missing_deps:
            print(
                f"⚠️  Missing audio dependencies: {', '.join(missing_deps)}. "
                f"Automatically enabling mocks."
            )
            apply_audio_mocks()
        else:
            print("✅ Real audio dependencies available. Using real libraries.")


def pytest_unconfigure():
    """Clean up after pytest run."""
    if MOCK_AUDIO_DEPENDENCIES or check_audio_dependencies():
        remove_audio_mocks()


# Apply mocks immediately if this module is imported directly
# (for backwards compatibility with existing scripts)
if __name__ != "__main__" and MOCK_AUDIO_DEPENDENCIES:
    apply_audio_mocks()
