"""Tests for text_to_audio utility functions."""

import unittest
from unittest.mock import MagicMock, patch, PropertyMock
import requests
from requests.exceptions import RequestException
from django.test import TestCase

from text_to_audio.utils import (
    extract_article_text,
    fetch_url_content,
    _fetch_url_with_headless_browser,  # Import private function for direct testing
    process_url_to_text,
)

# Attempt to import PlaywrightError, fail gracefully if playwright is not installed
try:
    from playwright.sync_api import Error as PlaywrightError
except ImportError:
    PlaywrightError = None  # Define as None if not available


class FetchUrlContentTests(TestCase):
    """Test suite for fetch_url_content and related functions."""

    @patch("text_to_audio.utils._fetch_url_with_headless_browser")
    @patch("text_to_audio.utils.requests.get")
    def test_fetch_url_content_requests_success(self, mock_requests_get, mock_playwright_fetch):
        """Test fetch_url_content when requests.get succeeds."""
        mock_response = MagicMock(spec=requests.Response)
        mock_response.status_code = 200
        mock_response.text = "sample HTML content"
        mock_requests_get.return_value = mock_response

        success, content, error_msg = fetch_url_content("http://example.com")

        self.assertTrue(success)
        self.assertEqual(content, "sample HTML content")
        self.assertIsNone(error_msg)
        mock_requests_get.assert_called_once_with("http://example.com", timeout=10)
        mock_playwright_fetch.assert_not_called()

    @patch("text_to_audio.utils._fetch_url_with_headless_browser")
    @patch("text_to_audio.utils.requests.get")
    def test_fetch_url_content_requests_fail_playwright_success(
        self, mock_requests_get, mock_playwright_fetch
    ):
        """Test fetch_url_content when requests.get fails (403) and Playwright succeeds."""
        mock_response = MagicMock(spec=requests.Response)
        mock_response.status_code = 403
        # Simulate the error message _handle_http_error would generate
        mock_response.url = "http://example.com"
        mock_requests_get.return_value = mock_response

        mock_playwright_fetch.return_value = (True, "playwright content", None)

        success, content, error_msg = fetch_url_content("http://example.com")

        self.assertTrue(success)
        self.assertEqual(content, "playwright content")
        self.assertIsNone(error_msg)
        mock_requests_get.assert_called_once_with("http://example.com", timeout=10)
        mock_playwright_fetch.assert_called_once_with("http://example.com")

    @patch("text_to_audio.utils._fetch_url_with_headless_browser")
    @patch("text_to_audio.utils.requests.get")
    def test_fetch_url_content_requests_fail_playwright_fail(
        self, mock_requests_get, mock_playwright_fetch
    ):
        """Test fetch_url_content when both requests.get (403) and Playwright fail."""
        mock_response = MagicMock(spec=requests.Response)
        mock_response.status_code = 403
        mock_response.url = "http://example.com" # Needed for _handle_http_error
        mock_requests_get.return_value = mock_response

        # This is what _handle_http_error would return for a 403
        expected_requests_error = f"403 Forbidden: Access to 'http://example.com' is forbidden. The site may require authentication or block automated access."

        mock_playwright_fetch.return_value = (False, "", "Playwright error")

        success, content, error_msg = fetch_url_content("http://example.com")

        self.assertFalse(success)
        self.assertEqual(content, "")
        expected_combined_error = (
            f"Initial request failed: {expected_requests_error}. "
            f"Playwright fallback also failed: Playwright error"
        )
        self.assertEqual(error_msg, expected_combined_error)
        mock_requests_get.assert_called_once_with("http://example.com", timeout=10)
        mock_playwright_fetch.assert_called_once_with("http://example.com")

    @patch("text_to_audio.utils._fetch_url_with_headless_browser")
    @patch("text_to_audio.utils.requests.get")
    def test_fetch_url_content_requests_permanent_error_no_fallback(
        self, mock_requests_get, mock_playwright_fetch
    ):
        """Test fetch_url_content with a non-fallback error (e.g., 404) from requests.get."""
        mock_response = MagicMock(spec=requests.Response)
        mock_response.status_code = 404
        mock_response.url = "http://example.com/notfound" # Needed for _handle_http_error
        mock_requests_get.return_value = mock_response

        success, content, error_msg = fetch_url_content("http://example.com/notfound")

        self.assertFalse(success)
        self.assertEqual(content, "")
        expected_error = f"404 Not Found: The requested page 'http://example.com/notfound' could not be found."
        self.assertEqual(error_msg, expected_error)
        mock_requests_get.assert_called_once_with("http://example.com/notfound", timeout=10)
        mock_playwright_fetch.assert_not_called()

    @patch("text_to_audio.utils.requests.get")
    def test_fetch_url_content_requests_exception(self, mock_requests_get):
        """Test fetch_url_content when requests.get raises an exception."""
        mock_requests_get.side_effect = RequestException("Network error")

        success, content, error_msg = fetch_url_content("http://example.com")

        self.assertFalse(success)
        self.assertEqual(content, "")
        # The error message now includes max_retries information
        self.assertIn("Failed after 5 attempts: Connection Error", error_msg)
        mock_requests_get.assert_called_with("http://example.com", timeout=10)
        self.assertEqual(mock_requests_get.call_count, 5) # Default max_retries is 5


@unittest.skipIf(PlaywrightError is None, "Playwright not installed, skipping Playwright specific tests")
class PlaywrightUtilTests(TestCase):
    """Test suite for _fetch_url_with_headless_browser."""

    @patch("text_to_audio.utils.sync_playwright")
    def test_fetch_url_with_headless_browser_success(self, mock_sync_playwright):
        """Test _fetch_url_with_headless_browser successfully fetches content."""
        mock_playwright_context = MagicMock()
        mock_browser = MagicMock()
        mock_page = MagicMock()

        mock_sync_playwright.return_value.__enter__.return_value = mock_playwright_context
        mock_playwright_context.chromium.launch.return_value = mock_browser
        mock_browser.new_page.return_value = mock_page
        mock_page.content.return_value = "mocked page content"

        success, content, error_msg = _fetch_url_with_headless_browser("http://example.com")

        self.assertTrue(success)
        self.assertEqual(content, "mocked page content")
        self.assertIsNone(error_msg)
        mock_playwright_context.chromium.launch.assert_called_once()
        mock_browser.new_page.assert_called_once()
        mock_page.goto.assert_called_once_with("http://example.com", timeout=30000)
        mock_page.content.assert_called_once()
        mock_browser.close.assert_called_once()

    @patch("text_to_audio.utils.sync_playwright")
    def test_fetch_url_with_headless_browser_playwright_error_on_goto(self, mock_sync_playwright):
        """Test _fetch_url_with_headless_browser handles PlaywrightError during page.goto()."""
        mock_playwright_context = MagicMock()
        mock_browser = MagicMock()
        mock_page = MagicMock()

        mock_sync_playwright.return_value.__enter__.return_value = mock_playwright_context
        mock_playwright_context.chromium.launch.return_value = mock_browser
        mock_browser.new_page.return_value = mock_page
        mock_page.goto.side_effect = PlaywrightError("Navigation failed")

        success, content, error_msg = _fetch_url_with_headless_browser("http://example.com")

        self.assertFalse(success)
        self.assertEqual(content, "")
        self.assertEqual(error_msg, "Playwright error: Navigation failed")
        mock_browser.close.assert_called_once() # Ensure browser is closed even on error

    @patch("text_to_audio.utils.sync_playwright")
    def test_fetch_url_with_headless_browser_playwright_error_on_launch(self, mock_sync_playwright):
        """Test _fetch_url_with_headless_browser handles PlaywrightError during launch."""
        mock_playwright_context = MagicMock()
        mock_sync_playwright.return_value.__enter__.return_value = mock_playwright_context
        mock_playwright_context.chromium.launch.side_effect = PlaywrightError("Launch failed")

        success, content, error_msg = _fetch_url_with_headless_browser("http://example.com")

        self.assertFalse(success)
        self.assertEqual(content, "")
        self.assertEqual(error_msg, "Playwright error: Launch failed")
        # No browser.close() to call if launch fails

    @patch("text_to_audio.utils.sync_playwright")
    def test_fetch_url_with_headless_browser_unexpected_error(self, mock_sync_playwright):
        """Test _fetch_url_with_headless_browser handles unexpected error."""
        mock_playwright_context = MagicMock()
        mock_sync_playwright.return_value.__enter__.return_value = mock_playwright_context
        mock_playwright_context.chromium.launch.side_effect = Exception("Unexpected boom")

        success, content, error_msg = _fetch_url_with_headless_browser("http://example.com")

        self.assertFalse(success)
        self.assertEqual(content, "")
        self.assertEqual(error_msg, "Unexpected Playwright error: Unexpected boom")


class ArticleExtractionTests(TestCase):
    """Test article extraction utility functions."""
    # Renamed from UrlUtilsTests to be more specific
        """Test extracting article text from HTML content."""
        # Create test HTML with article content
        html = """
        <html>
            <body>
                <article>
                    <h1>Test Article</h1>
                    <p>This is a test paragraph.</p>
                    <p>This is another paragraph.</p>
                    <img src="test.jpg" alt="Test image">
                    <table>
                        <caption>Test Table</caption>
                        <tr><td>Data</td></tr>
                    </table>
                </article>
            </body>
        </html>
        """

        # Call the function
        success, text, error = extract_article_text(html)

        # Assert results
        self.assertTrue(success)
        self.assertIn("Test Article", text)
        self.assertIn("This is a test paragraph.", text)
        self.assertIn("This is another paragraph.", text)
        self.assertIn("[Image: Test image]", text)
        self.assertIn("[Table: Test Table]", text)
        self.assertIsNone(error)

    def test_extract_article_text_no_content(self):
        """Test extracting text from HTML with no meaningful content."""
        # HTML with no article content
        html = "<html><body></body></html>"

        # Call the function
        success, text, error = extract_article_text(html)

        # Assert results
        self.assertFalse(success)
        self.assertEqual(text, "")
        self.assertIsNotNone(error)

    @patch("text_to_audio.utils.fetch_url_content")
    @patch("text_to_audio.utils.extract_article_text_with_gpt") # Mocking GPT based extraction
    @patch("text_to_audio.utils.extract_article_text") # Mocking traditional extraction
    @patch("text_to_audio.utils.fetch_url_content")
    @patch("django.conf.settings") # To control USE_GPT_FOR_URL_EXTRACTION
    def test_process_url_to_text_success_with_gpt(self, mock_settings, mock_fetch, mock_extract_traditional, mock_extract_gpt):
        """Test the full URL processing flow with success using GPT."""
        # Setup mocks
        mock_settings.USE_GPT_FOR_URL_EXTRACTION = True
        mock_fetch.return_value = (True, "html content", None)
        mock_extract_gpt.return_value = (True, "GPT Extracted text", None)

        # Call the function
        success, text, error = process_url_to_text("https://example.com")

        # Assert results
        self.assertTrue(success)
        self.assertEqual(text, "GPT Extracted text")
        self.assertIsNone(error)
        mock_fetch.assert_called_once_with("https://example.com")
        mock_extract_gpt.assert_called_once_with("html content", "https://example.com")
        mock_extract_traditional.assert_not_called()

    @patch("text_to_audio.utils.extract_article_text_with_gpt")
    @patch("text_to_audio.utils.extract_article_text")
    @patch("text_to_audio.utils.fetch_url_content")
    @patch("django.conf.settings")
    def test_process_url_to_text_success_fallback_to_traditional(self, mock_settings, mock_fetch, mock_extract_traditional, mock_extract_gpt):
        """Test GPT failure and fallback to traditional extraction."""
        mock_settings.USE_GPT_FOR_URL_EXTRACTION = True
        mock_fetch.return_value = (True, "html content", None)
        mock_extract_gpt.return_value = (False, "", "GPT Error") # GPT fails
        mock_extract_traditional.return_value = (True, "Traditional Extracted text", None) # Traditional succeeds

        success, text, error = process_url_to_text("https://example.com")

        self.assertTrue(success)
        self.assertEqual(text, "Traditional Extracted text")
        self.assertIsNone(error)
        mock_fetch.assert_called_once_with("https://example.com")
        mock_extract_gpt.assert_called_once_with("html content", "https://example.com")
        mock_extract_traditional.assert_called_once_with("html content")

    @patch("text_to_audio.utils.extract_article_text") # Only traditional extraction
    @patch("text_to_audio.utils.fetch_url_content")
    @patch("django.conf.settings")
    def test_process_url_to_text_success_traditional_only(self, mock_settings, mock_fetch, mock_extract_traditional):
        """Test success with traditional extraction when GPT is disabled."""
        mock_settings.USE_GPT_FOR_URL_EXTRACTION = False # GPT disabled
        mock_fetch.return_value = (True, "html content", None)
        mock_extract_traditional.return_value = (True, "Traditional Extracted text", None)

        success, text, error = process_url_to_text("https://example.com")

        self.assertTrue(success)
        self.assertEqual(text, "Traditional Extracted text")
        self.assertIsNone(error)
        mock_fetch.assert_called_once_with("https://example.com")
        mock_extract_traditional.assert_called_once_with("html content")


    @patch("text_to_audio.utils.fetch_url_content")
    @patch("django.conf.settings")
    def test_process_url_to_text_fetch_failure(self, mock_settings, mock_fetch):
        """Test URL processing with fetch failure."""
        """Test URL processing with fetch failure."""
        mock_settings.USE_GPT_FOR_URL_EXTRACTION = True # Does not matter here
        # Setup mock to simulate fetch failure
        mock_fetch.return_value = (False, "", "Fetch error")

        # Call the function
        success, text, error = process_url_to_text("https://example.com")

        # Assert results
        self.assertFalse(success)
        self.assertEqual(text, "")
        self.assertEqual(error, "Fetch error")
        mock_fetch.assert_called_once_with("https://example.com")


if __name__ == "__main__":
    unittest.main()
