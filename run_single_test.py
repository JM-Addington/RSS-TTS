#!/usr/bin/env python
"""Run a specific test file with mocks for audio dependencies."""

import os
import sys

from django.conf import settings
from django.test.runner import DiscoverRunner

# Import the mock configuration before any other imports
import tests.conftest_mock  # noqa

if __name__ == "__main__":
    # Check arguments
    if len(sys.argv) < 2:
        print("Usage: python run_single_test.py <test_file_path>")
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
