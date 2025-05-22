"""Tests for the pre-commit setup script."""

import os
import stat
import unittest


class TestPrecommitSetup(unittest.TestCase):
    """Validate the setup_precommit.sh script."""

    SCRIPT_PATH = os.path.join(
        os.path.dirname(os.path.dirname(__file__)), "setup_precommit.sh"
    )

    def test_script_exists(self):
        """Ensure the script file exists."""
        self.assertTrue(
            os.path.isfile(self.SCRIPT_PATH), "setup_precommit.sh should exist"
        )

    def test_script_executable(self):
        """Ensure the script is executable."""
        if not os.path.isfile(self.SCRIPT_PATH):
            self.skipTest("setup_precommit.sh missing")
        st = os.stat(self.SCRIPT_PATH)
        self.assertTrue(
            st.st_mode & stat.S_IEXEC, "setup_precommit.sh should be executable"
        )

    def test_script_contains_commands(self):
        """Check that the script installs and configures pre-commit."""
        if not os.path.isfile(self.SCRIPT_PATH):
            self.skipTest("setup_precommit.sh missing")
        with open(self.SCRIPT_PATH, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("pre-commit install", content)
        self.assertIn("pip install pre-commit", content)


if __name__ == "__main__":
    unittest.main()
