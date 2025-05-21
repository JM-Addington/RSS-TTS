import os
from django.conf import settings
from django.test import Client, TestCase


class TestFrontendTemplates(TestCase):
    """Tests for basic frontend templates and views."""

    def setUp(self):
        self.client = Client()

    def _template_path(self, relative):
        return os.path.join(settings.BASE_DIR, "text_to_audio", "templates", *relative.split("/"))

    def test_base_template_exists(self):
        self.assertTrue(os.path.isfile(self._template_path("base.html")), "base.html not found")

    def test_partial_templates_exist(self):
        for name in ("partials/_nav.html", "partials/_header.html", "partials/_footer.html"):
            self.assertTrue(os.path.isfile(self._template_path(name)), f"{name} not found")

    def test_home_view_renders(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "index.html")
