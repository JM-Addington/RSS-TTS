"""Tests for text_to_audio utility functions."""

import unittest
from unittest.mock import MagicMock, patch

from django.test import TestCase

from text_to_audio.utils import (
    extract_article_text,
    fetch_url_content,
    process_url_to_text,
)


class UrlUtilsTests(TestCase):
    """Test URL processing utility functions."""

    @patch("text_to_audio.utils.requests.get")
    def test_fetch_url_content_success(self, mock_get):
        """Test fetching URL content successfully."""
        # Setup mock response
        mock_response = MagicMock()
        mock_response.text = (
            "<html><body><article>Test article content</article></body></html>"
        )
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        # Call the function
        success, content, error = fetch_url_content("https://example.com")

        # Assert results
        self.assertTrue(success)
        self.assertEqual(content, mock_response.text)
        self.assertIsNone(error)
        mock_get.assert_called_once_with("https://example.com", timeout=10)
        mock_response.raise_for_status.assert_called_once()

    @patch("text_to_audio.utils.requests.get")
    def test_fetch_url_content_failure(self, mock_get):
        """Test handling of a failed URL fetch."""
        # Setup mock to raise an exception
        mock_get.side_effect = Exception("Connection error")

        # Call the function
        success, content, error = fetch_url_content("https://example.com")

        # Assert results
        self.assertFalse(success)
        self.assertEqual(content, "")
        self.assertIsNotNone(error)
        if error:
            self.assertIn("Connection error", error)
        mock_get.assert_called_once_with("https://example.com", timeout=10)

    def test_extract_article_text_success(self):
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
    @patch("text_to_audio.utils.extract_article_text")
    def test_process_url_to_text_success(self, mock_extract, mock_fetch):
        """Test the full URL processing flow with success."""
        # Setup mocks
        mock_fetch.return_value = (True, "html content", None)
        mock_extract.return_value = (True, "Extracted text", None)

        # Call the function
        success, text, error = process_url_to_text("https://example.com")

        # Assert results
        self.assertTrue(success)
        self.assertEqual(text, "Extracted text")
        self.assertIsNone(error)
        mock_fetch.assert_called_once_with("https://example.com")
        mock_extract.assert_called_once_with("html content")

    @patch("text_to_audio.utils.fetch_url_content")
    def test_process_url_to_text_fetch_failure(self, mock_fetch):
        """Test URL processing with fetch failure."""
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
