#!/usr/bin/env python
"""Run all tests with mocks for audio dependencies.

This script explicitly enables audio dependency mocking by setting
MOCK_AUDIO_DEPENDENCIES=true before importing the test configuration.
"""

import os
import sys
from pathlib import Path

# Enable audio mocking explicitly
os.environ["MOCK_AUDIO_DEPENDENCIES"] = "true"

from django.conf import settings
from django.test.runner import DiscoverRunner

# Import the mock configuration after setting the environment variable
import tests.conftest_mock  # noqa

if __name__ == "__main__":
    print("🎭 RSS-TTS Test Runner with Audio Mocking")
    print("===========================================")
    print(f"Audio mocking enabled: {os.environ.get('MOCK_AUDIO_DEPENDENCIES')}")
    print()

    # Set up the test environment
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "rss_tts.settings")
    settings.TESTING = True

    # Find all test modules
    test_modules = []
    tests_dir = Path(__file__).parent / "tests"

    # Add root test files
    for file in tests_dir.glob("test_*.py"):
        module_path = f"tests.{file.stem}"
        test_modules.append(module_path)

    # Add subdirectory test files
    for file in tests_dir.glob("**/test_*.py"):
        if file.is_file():
            relative_path = file.relative_to(Path(__file__).parent)
            module_path = str(relative_path).replace("/", ".").replace(".py", "")
            test_modules.append(module_path)

    print(f"Found {len(test_modules)} test modules to run:")
    for module in test_modules:
        print(f" - {module}")

    # Run the tests
    test_runner = DiscoverRunner(verbosity=2)
    failures = test_runner.run_tests(test_modules)

    sys.exit(bool(failures))
