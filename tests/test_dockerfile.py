"""Tests for the Dockerfile configuration."""

import os
import unittest


class TestDockerfile(unittest.TestCase):
    """Test that the Dockerfile exists and contains required instructions."""

    def setUp(self):
        """Set up the test environment by locating the Dockerfile path."""
        self.dockerfile_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "Dockerfile"
        )

    def test_dockerfile_exists(self):
        """Ensure Dockerfile exists at project root."""
        self.assertTrue(
            os.path.isfile(self.dockerfile_path),
            "Dockerfile should exist at project root",
        )

    def test_python_version(self):
        """Verify Python 3.12 is used as the base image."""
        if not os.path.isfile(self.dockerfile_path):
            self.skipTest("Dockerfile missing")
        with open(self.dockerfile_path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn(
            "python:3.12", content, "Dockerfile should use Python 3.12 base image"
        )

    def test_install_celery(self):
        """Verify Celery is installed in the requirements.txt file."""
        requirements_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "requirements.txt"
        )
        if not os.path.isfile(requirements_path):
            self.skipTest("requirements.txt missing")
        with open(requirements_path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn(
            "celery", content.lower(), "requirements.txt should include Celery"
        )

    def test_install_redis(self):
        """Verify redis-server is installed in the Dockerfile."""
        if not os.path.isfile(self.dockerfile_path):
            self.skipTest("Dockerfile missing")
        with open(self.dockerfile_path, "r", encoding="utf-8") as f:
            content = f.read().lower()
        self.assertIn("redis-server", content, "Dockerfile should install redis-server")

    def test_expose_port(self):
        """Verify port 8000 is exposed in the Dockerfile."""
        if not os.path.isfile(self.dockerfile_path):
            self.skipTest("Dockerfile missing")
        with open(self.dockerfile_path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("EXPOSE 8000", content, "Dockerfile should expose port 8000")


if __name__ == "__main__":
    unittest.main()
