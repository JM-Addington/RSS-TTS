"""Tests that verify the project structure and required files exist."""

import glob
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

        self.assertIn("features", data)
        self.assertIn(
            "ghcr.io/devcontainers/features/docker-in-docker:2.12.2", data["features"]
        )
        self.assertIn("remoteUser", data)
        self.assertEqual("vscode", data["remoteUser"])

    def test_docker_compose_has_redis_service(self):
        """Ensure docker-compose.yml defines a redis service."""
        with open("docker-compose.yml", "r", encoding="utf-8") as f:
            compose_content = f.read()

        import yaml

        compose_data = yaml.safe_load(compose_content)
        self.assertIn("redis", compose_data.get("services", {}))

    def test_dead_template_feed_form_improved_removed(self):
        """Verify that the dead template feed_form_improved.html does not exist."""
        self.assertFalse(
            os.path.isfile(
                os.path.join("text_to_audio", "templates", "feed_form_improved.html")
            ),
            "feed_form_improved.html should be removed — it is dead code",
        )

    def test_no_references_to_feed_form_improved(self):
        """Verify no .py or .html files reference feed_form_improved."""
        # AIDEV-NOTE: excludes tests/ and .ralph/ to avoid false positives
        search_patterns = ["**/*.py", "**/*.html"]
        exclude_dirs = {"tests", ".ralph", "__pycache__"}
        for pattern in search_patterns:
            for filepath in glob.glob(pattern, recursive=True):
                # Skip files in excluded directories
                parts = filepath.split(os.sep)
                if any(part in exclude_dirs for part in parts):
                    continue
                # Skip the dead template itself (may still exist during red phase)
                if filepath.endswith("feed_form_improved.html"):
                    continue
                with open(filepath, encoding="utf-8", errors="ignore") as f:
                    content = f.read()
                self.assertNotIn(
                    "feed_form_improved",
                    content,
                    f"Found reference to feed_form_improved in {filepath}",
                )


if __name__ == "__main__":
    unittest.main()
