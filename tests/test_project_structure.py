import os
import unittest


class TestProjectStructure(unittest.TestCase):
    def test_manage_py_exists(self):
        self.assertTrue(os.path.isfile("manage.py"))

    def test_settings_exists(self):
        self.assertTrue(os.path.isfile(os.path.join("rss_tts", "settings.py")))

    def test_docker_compose_exists(self):
        self.assertTrue(os.path.isfile("docker-compose.yml"))

    def test_devcontainer_updated(self):
        import json

        with open(os.path.join(".devcontainer", "devcontainer.json")) as f:
            data = json.load(f)

        self.assertIn("runServices", data)


if __name__ == "__main__":
    unittest.main()
