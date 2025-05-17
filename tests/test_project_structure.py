import os
import unittest


class TestProjectStructure(unittest.TestCase):
    def test_manage_py_exists(self):
        self.assertTrue(os.path.isfile('manage.py'))

    def test_settings_exists(self):
        self.assertTrue(os.path.isfile(os.path.join('rss_tts', 'settings.py')))


if __name__ == '__main__':
    unittest.main()
