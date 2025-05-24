#!/usr/bin/env python
"""Run tests with mocks for audio dependencies."""

import os
import sys

from django.conf import settings
from django.test.runner import DiscoverRunner

# Import the mock configuration before any other imports
import tests.conftest_mock  # noqa

if __name__ == "__main__":
    # Set up the test environment
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "rss_tts.settings")
    settings.TESTING = True

    # Run the tests
    test_runner = DiscoverRunner(verbosity=2)
    failures = test_runner.run_tests(["tests"])

    sys.exit(bool(failures))
