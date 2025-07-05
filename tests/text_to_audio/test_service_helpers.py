# flake8: noqa
# mypy: ignore-errors
"""Unit tests for private service helper methods."""

from django.test import TestCase, override_settings

from text_to_audio.services.content_analysis import ContentAnalysisService
from text_to_audio.services.genre_classification import GenreClassificationService


class ServiceHelperFunctionTests(TestCase):
    """Tests for internal service helper methods."""

    def test_create_analysis_prompt_includes_text_and_title(self):
        """Prompt includes provided text and title."""
        service = ContentAnalysisService()
        prompt = service._create_analysis_prompt("sample text", "My Title")
        self.assertIn("sample text", prompt)
        self.assertIn("My Title", prompt)

    @override_settings(OPENAI_ANALYSIS_MODEL="custom-model")
    def test_get_analysis_model_uses_setting(self):
        """Analysis model pulled from settings."""
        service = ContentAnalysisService()
        self.assertEqual(service._get_analysis_model(), "custom-model")

    def test_create_classification_prompt_includes_text_and_title(self):
        """Classification prompt contains text and title."""
        service = GenreClassificationService()
        prompt = service._create_classification_prompt("text here", "Title")
        self.assertIn("text here", prompt)
        self.assertIn("Title", prompt)

    @override_settings(OPENAI_CLASSIFICATION_MODEL="model-x")
    def test_get_classification_model_uses_setting(self):
        """Classification model pulled from settings."""
        service = GenreClassificationService()
        self.assertEqual(service._get_classification_model(), "model-x")
