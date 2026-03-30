"""Tests for CSS extraction from inline styles to external stylesheets (issue #234)."""

import os
from pathlib import Path

from django.test import TestCase

# AIDEV-NOTE: Base directories for static files and templates
BASE_DIR = Path(__file__).resolve().parent.parent


class CSSFileExistenceTests(TestCase):
    """Verify that extracted CSS files exist at expected paths."""

    def test_cost_analytics_css_exists(self):
        path = BASE_DIR / "text_to_audio/static/text_to_audio/css/cost_analytics.css"
        self.assertTrue(path.exists(), f"Expected CSS file at {path}")

    def test_article_list_css_exists(self):
        path = BASE_DIR / "text_to_audio/static/text_to_audio/css/article_list.css"
        self.assertTrue(path.exists(), f"Expected CSS file at {path}")

    def test_global_config_css_exists(self):
        path = BASE_DIR / "accounts/static/accounts/css/global_config.css"
        self.assertTrue(path.exists(), f"Expected CSS file at {path}")


class CSSContentTests(TestCase):
    """Verify CSS files contain the expected selectors."""

    def test_cost_analytics_css_selectors(self):
        path = BASE_DIR / "text_to_audio/static/text_to_audio/css/cost_analytics.css"
        content = path.read_text()
        self.assertIn(".cost-card", content)
        self.assertIn(".cost-card.total", content)
        self.assertIn(".cost-card.llm", content)
        self.assertIn(".cost-card.tts", content)
        self.assertIn(".chart-container", content)
        self.assertIn(".table-costs td.cost", content)
        self.assertIn(".date-filter", content)

    def test_article_list_css_selectors(self):
        path = BASE_DIR / "text_to_audio/static/text_to_audio/css/article_list.css"
        content = path.read_text()
        self.assertIn("tr.now-playing", content)
        self.assertIn("!important", content)

    def test_global_config_css_selectors(self):
        path = BASE_DIR / "accounts/static/accounts/css/global_config.css"
        content = path.read_text()
        self.assertIn(".form-control", content)
        self.assertIn(".card-header h5", content)
        self.assertIn(".form-text", content)


class TemplateContentTests(TestCase):
    """Verify templates no longer have inline <style> and reference external CSS."""

    def test_cost_analytics_no_inline_style(self):
        path = BASE_DIR / "text_to_audio/templates/text_to_audio/cost_analytics.html"
        content = path.read_text()
        self.assertNotIn("<style>", content)
        self.assertNotIn("</style>", content)

    def test_cost_analytics_references_css(self):
        path = BASE_DIR / "text_to_audio/templates/text_to_audio/cost_analytics.html"
        content = path.read_text()
        self.assertIn("text_to_audio/css/cost_analytics.css", content)

    def test_article_list_no_inline_style(self):
        path = BASE_DIR / "text_to_audio/templates/article_list.html"
        content = path.read_text()
        self.assertNotIn("<style>", content)
        self.assertNotIn("</style>", content)

    def test_article_list_references_css(self):
        path = BASE_DIR / "text_to_audio/templates/article_list.html"
        content = path.read_text()
        self.assertIn("text_to_audio/css/article_list.css", content)

    def test_article_list_has_load_static(self):
        path = BASE_DIR / "text_to_audio/templates/article_list.html"
        content = path.read_text()
        # static should be loaded (either standalone or combined with other tags)
        self.assertTrue(
            "{% load static %}" in content or "{% load i18n static %}" in content,
            "Template must load the 'static' template tag library",
        )

    def test_global_config_no_inline_style(self):
        path = BASE_DIR / "accounts/templates/accounts/global_config.html"
        content = path.read_text()
        self.assertNotIn("<style>", content)
        self.assertNotIn("</style>", content)

    def test_global_config_references_css(self):
        path = BASE_DIR / "accounts/templates/accounts/global_config.html"
        content = path.read_text()
        self.assertIn("accounts/css/global_config.css", content)

    def test_global_config_has_load_static(self):
        path = BASE_DIR / "accounts/templates/accounts/global_config.html"
        content = path.read_text()
        self.assertIn("{% load static %}", content)
