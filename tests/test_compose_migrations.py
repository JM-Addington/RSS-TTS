import unittest
import yaml


class TestComposeMigrations(unittest.TestCase):
    """Ensure production compose runs migrations."""

    def setUp(self):
        with open("docker-compose.prod.yml", "r", encoding="utf-8") as f:
            self.compose = yaml.safe_load(f)

    def test_web_service_runs_migrations(self):
        cmd = self.compose["services"]["web"].get("command", "")
        self.assertIn(
            "/app/start-web.sh",
            cmd,
            "web service should use start-web.sh to apply migrations",
        )

    def test_worker_service_runs_migrations(self):
        cmd = self.compose["services"]["worker"].get("command", "")
        self.assertIn(
            "/app/start-web.sh",
            cmd,
            "worker service should use start-web.sh to apply migrations",
        )


if __name__ == "__main__":
    unittest.main()
