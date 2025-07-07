"""Tests for Firecrawl fallback and default usage."""

from unittest.mock import patch

from django.test import TestCase, override_settings

from text_to_audio.utils import process_url_to_text


class FirecrawlTests(TestCase):
    """Firecrawl integration tests for URL processing."""

    @override_settings(FIRECRAWL_API_KEY="key", USE_FIRECRAWL_BY_DEFAULT=True)
    @patch("appconfig.utils.get_use_firecrawl_by_default", return_value=True)
    @patch("appconfig.utils.get_firecrawl_api_key", return_value="key")
    @patch("text_to_audio.utils.fetch_url_content")
    @patch("text_to_audio.utils.fetch_html_with_firecrawl")
    @patch("text_to_audio.utils.extract_article_text_with_gpt")
    def test_use_firecrawl_by_default(self, mock_extract, mock_firecrawl, mock_fetch, mock_api_key, mock_use_default):
        """Firecrawl should be used when enabled by default."""
        mock_firecrawl.return_value = (True, "<html></html>", None)
        mock_extract.return_value = (True, "txt", None)
        mock_fetch.return_value = (True, "backup html", None)  # Should not be called, but set up just in case

        success, text, error = process_url_to_text("https://example.com")

        self.assertTrue(success)
        self.assertEqual(text, "txt")
        self.assertIsNone(error)
        mock_firecrawl.assert_called_once_with("https://example.com")
        mock_extract.assert_called_once_with("<html></html>", "https://example.com")
        mock_fetch.assert_not_called()

    @override_settings(FIRECRAWL_API_KEY="key", USE_FIRECRAWL_BY_DEFAULT=False)
    @patch("appconfig.utils.get_use_firecrawl_by_default", return_value=False)
    @patch("appconfig.utils.get_firecrawl_api_key", return_value="key")
    @patch("text_to_audio.utils.fetch_url_content")
    @patch("text_to_audio.utils.fetch_html_with_firecrawl")
    @patch("text_to_audio.utils.extract_article_text_with_gpt")
    def test_firecrawl_fallback_on_4xx(self, mock_extract, mock_firecrawl, mock_fetch, mock_api_key, mock_use_default):
        """Firecrawl should be used when direct fetch returns 4xx."""
        mock_fetch.return_value = (
            False,
            "",
            "404 Not Found: The requested page could not be found.",
        )
        mock_firecrawl.return_value = (True, "<html></html>", None)
        mock_extract.return_value = (True, "txt", None)

        success, text, error = process_url_to_text("https://example.com")

        self.assertTrue(success)
        self.assertEqual(text, "txt")
        self.assertIsNone(error)
        mock_fetch.assert_called_once_with("https://example.com", max_retries=1)
        mock_firecrawl.assert_called_once_with("https://example.com")
        mock_extract.assert_called_once_with("<html></html>", "https://example.com")
