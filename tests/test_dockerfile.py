import os
import unittest


class TestDockerfile(unittest.TestCase):
    """Test that the Dockerfile exists and contains required instructions."""

    def setUp(self):
        self.dockerfile_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "Dockerfile"
        )

    def test_dockerfile_exists(self):
        self.assertTrue(
            os.path.isfile(self.dockerfile_path),
            "Dockerfile should exist at project root",
        )

    def test_python_version(self):
        if not os.path.isfile(self.dockerfile_path):
            self.skipTest("Dockerfile missing")
        with open(self.dockerfile_path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn(
            "python:3.12", content, "Dockerfile should use Python 3.12 base image"
        )

    def test_install_celery(self):
        if not os.path.isfile(self.dockerfile_path):
            self.skipTest("Dockerfile missing")
        with open(self.dockerfile_path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("celery", content.lower(), "Dockerfile should install Celery")


if __name__ == "__main__":
    unittest.main()
