"""Tests for CSS extraction from inline styles to external stylesheets (issue #234)."""

import re
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

    def test_voice_preset_form_no_inline_style_block(self):
        path = BASE_DIR / "text_to_audio/templates/text_to_audio/voice_preset_form.html"
        content = path.read_text()
        self.assertNotIn("<style>", content)
        self.assertNotIn("</style>", content)

    def test_voice_preset_form_references_css(self):
        path = BASE_DIR / "text_to_audio/templates/text_to_audio/voice_preset_form.html"
        content = path.read_text()
        self.assertIn("text_to_audio/css/voice_preset_form.css", content)

    def test_voice_preset_form_has_load_static(self):
        path = BASE_DIR / "text_to_audio/templates/text_to_audio/voice_preset_form.html"
        content = path.read_text()
        self.assertTrue(
            "{% load static %}" in content
            or "{% load i18n static %}" in content
            or "{% load static i18n %}" in content,
            "Template must load the 'static' template tag library",
        )


class CSSFileExistenceVoicePresetTests(TestCase):
    """Verify voice_preset_form.css exists."""

    def test_voice_preset_form_css_exists(self):
        path = BASE_DIR / "text_to_audio/static/text_to_audio/css/voice_preset_form.css"
        self.assertTrue(path.exists(), f"Expected CSS file at {path}")


class CSSContentVoicePresetTests(TestCase):
    """Verify voice_preset_form.css contains expected selectors."""

    def test_voice_preset_form_css_selectors(self):
        path = BASE_DIR / "text_to_audio/static/text_to_audio/css/voice_preset_form.css"
        content = path.read_text()
        self.assertIn("textarea", content)
        self.assertIn(".card", content)
        self.assertIn(".card-header", content)
        self.assertIn(".card-body", content)


class InlineStyleAttributeTests(TestCase):
    """Verify templates have no presentational inline style= attributes."""

    def _get_presentational_inline_styles(self, content):
        """Return style= attributes that are not on js-config divs."""
        # Find all style= occurrences with their surrounding context
        matches = []
        for match in re.finditer(r'style="[^"]*"', content):
            # Get surrounding context to check if it's on a js-config div
            start = max(0, match.start() - 200)
            context = content[start : match.end()]
            if 'id="js-config"' not in context:
                matches.append(match.group())
        return matches

    def test_article_list_no_presentational_inline_styles(self):
        path = BASE_DIR / "text_to_audio/templates/article_list.html"
        content = path.read_text()
        matches = self._get_presentational_inline_styles(content)
        self.assertEqual(
            matches,
            [],
            f"Found presentational inline styles in article_list.html: {matches}",
        )

    def test_global_config_no_inline_style_attributes(self):
        path = BASE_DIR / "accounts/templates/accounts/global_config.html"
        content = path.read_text()
        matches = re.findall(r'style="[^"]*"', content)
        self.assertEqual(
            matches,
            [],
            f"Found inline style attributes in global_config.html: {matches}",
        )

    def test_voice_preset_form_no_presentational_inline_styles(self):
        path = BASE_DIR / "text_to_audio/templates/text_to_audio/voice_preset_form.html"
        content = path.read_text()
        matches = self._get_presentational_inline_styles(content)
        self.assertEqual(
            matches,
            [],
            f"Found presentational inline styles in voice_preset_form.html: {matches}",
        )

    def test_article_list_css_has_audio_player_styles(self):
        path = BASE_DIR / "text_to_audio/static/text_to_audio/css/article_list.css"
        content = path.read_text()
        self.assertIn("#audioPlayerContainer", content)
        self.assertIn("#audioPlayer", content)
        self.assertIn(".source-url-link", content)

    def test_js_config_uses_d_none_class(self):
        """Verify js-config divs use d-none class instead of style='display:none'."""
        templates = [
            BASE_DIR / "text_to_audio/templates/article_list.html",
            BASE_DIR / "text_to_audio/templates/text_to_audio/voice_preset_form.html",
        ]
        for template_path in templates:
            content = template_path.read_text()
            if 'id="js-config"' in content:
                # Find the js-config div and check it uses d-none
                js_config_match = re.search(
                    r'<div\s+id="js-config"[^>]*>', content
                )
                self.assertIsNotNone(
                    js_config_match,
                    f"js-config div not found in {template_path.name}",
                )
                div_tag = js_config_match.group()
                self.assertIn(
                    "d-none",
                    div_tag,
                    f"js-config div in {template_path.name} should use d-none class",
                )
                self.assertNotIn(
                    'style=',
                    div_tag,
                    f"js-config div in {template_path.name} should not have inline style",
                )
