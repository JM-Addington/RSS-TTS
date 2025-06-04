#!/usr/bin/env python
"""Run a specific test file with conditional mocks for audio dependencies.

Usage:
    # Run with audio mocking enabled
    MOCK_AUDIO_DEPENDENCIES=true python run_single_test.py tests/test_models.py

    # Run with real audio libraries (if available)
    python run_single_test.py tests/test_models.py
"""

import os
import sys

# Set default mocking to true for this script (backwards compatibility)
os.environ.setdefault("MOCK_AUDIO_DEPENDENCIES", "true")

from django.conf import settings
from django.test.runner import DiscoverRunner

# Import the mock configuration after setting environment variables
import tests.conftest_mock  # noqa

if __name__ == "__main__":
    print("🎭 RSS-TTS Single Test Runner")
    print("==============================")
    print(f"Audio mocking enabled: {os.environ.get('MOCK_AUDIO_DEPENDENCIES')}")
    print()

    # Check arguments
    if len(sys.argv) < 2:
        print("Usage: python run_single_test.py <test_file_path>")
        print("")
        print("Examples:")
        print("  python run_single_test.py tests/test_models.py")
        print(
            "  MOCK_AUDIO_DEPENDENCIES=false python run_single_test.py tests/test_models.py"
        )
        sys.exit(1)

    test_path = sys.argv[1]

    # Set up the test environment
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "rss_tts.settings")
    settings.TESTING = True

    if test_path.endswith(".py"):
        # Convert file path to module path
        module_path = test_path.replace("/", ".").replace(".py", "")
        if module_path.startswith("."):
            module_path = module_path[1:]

        print(f"Running test module: {module_path}")

        # Run the test
        test_runner = DiscoverRunner(verbosity=2)
        failures = test_runner.run_tests([module_path])
    else:
        print(f"Invalid test file: {test_path}")
        sys.exit(1)

    sys.exit(bool(failures))
