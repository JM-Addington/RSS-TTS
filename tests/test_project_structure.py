"""Tests that verify the project structure and required files exist."""

import os
import unittest


class TestProjectStructure(unittest.TestCase):
    """Validates that important project files are present and properly configured."""

    def test_manage_py_exists(self):
        """Verify that manage.py exists at the project root."""
        self.assertTrue(os.path.isfile("manage.py"))

    def test_settings_exists(self):
        """Verify that the settings.py file exists in the rss_tts package."""
        self.assertTrue(os.path.isfile(os.path.join("rss_tts", "settings.py")))

    def test_docker_compose_exists(self):
        """Verify that the docker-compose.yml file exists."""
        self.assertTrue(os.path.isfile("docker-compose.yml"))

    def test_docker_compose_prod_exists(self):
        """Verify that the production docker-compose file exists."""
        self.assertTrue(os.path.isfile("docker-compose.prod.yml"))

    def test_dockerfile_exists(self):
        """Verify that the Dockerfile exists."""
        self.assertTrue(os.path.isfile("Dockerfile"))

    def test_env_sample_exists(self):
        """Verify that the .env.sample file exists."""
        self.assertTrue(os.path.isfile(".env.sample"))

    def test_dockerignore_exists(self):
        """Verify that the .dockerignore file exists."""
        self.assertTrue(os.path.isfile(".dockerignore"))

    def test_devcontainer_updated(self):
        """Verify that the devcontainer.json has the required configuration."""
        import json

        with open(os.path.join(".devcontainer", "devcontainer.json")) as f:
            data = json.load(f)

        self.assertIn("runServices", data)
        # Redis should now run inside a service container, so it is not a
        # separate service in runServices
        self.assertNotIn("redis", data["runServices"])

    def test_docker_compose_has_redis_service(self):
        """Ensure docker-compose.yml defines a redis service."""
        with open("docker-compose.yml", "r", encoding="utf-8") as f:
            compose_content = f.read()

        import yaml

        compose_data = yaml.safe_load(compose_content)
        self.assertIn("redis", compose_data.get("services", {}))


if __name__ == "__main__":
    unittest.main()
