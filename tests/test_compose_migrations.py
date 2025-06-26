"""Tests for Docker Compose migration configuration.

This module tests the Docker Compose configuration to ensure that
migrations will run automatically in production.
"""

import unittest

import yaml


class TestComposeProduction(unittest.TestCase):
    """Test cases for the docker-compose.prod.yml file."""

    def setUp(self):
        """Load the docker-compose.prod.yml file."""
        with open("docker-compose.prod.yml", "r") as file:
            self.compose_config = yaml.safe_load(file)

    def test_web_service_uses_start_web_script(self):
        """Test that the web service uses the start-web.sh script."""
        web_service = self.compose_config["services"]["web"]
        self.assertIn(
            "/app/start-web.sh",
            web_service["command"],
            "Web service should use start-web.sh to run migrations",
        )

    def test_worker_service_uses_start_worker_script(self):
        """Test that the worker service uses the start-worker.sh script."""
        worker_service = self.compose_config["services"]["worker"]
        self.assertIn(
            "/app/start-worker.sh",
            worker_service["command"],
            "Worker service should use start-worker.sh",
        )

    def test_worker_depends_on_redis(self):
        """Test that the worker service depends on Redis."""
        worker_service = self.compose_config["services"]["worker"]
        self.assertIn(
            "redis",
            worker_service["depends_on"],
            "Worker service should depend on Redis",
        )


if __name__ == "__main__":
    unittest.main()
