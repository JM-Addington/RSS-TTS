"""Tests for text_to_audio utility functions."""

import unittest
from unittest.mock import MagicMock, patch

import requests
from django.test import TestCase

from text_to_audio.utils import (
    extract_article_text,
    fetch_url_content,
    process_url_to_text,
    sanitize_text_for_tts,
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
        mock_response.status_code = 200
        mock_get.return_value = mock_response

        # Call the function
        success, content, error = fetch_url_content("https://example.com")

        # Assert results
        self.assertTrue(success)
        self.assertEqual(content, mock_response.text)
        self.assertIsNone(error)
        mock_get.assert_called_once_with("https://example.com", timeout=10)

    @patch("text_to_audio.utils.requests.get")
    @patch("text_to_audio.utils.requests.RequestException", new=Exception)
    def test_fetch_url_content_failure(self, mock_get):
        """Test handling of a failed URL fetch."""
        # Setup mock to return a proper exception that's handled
        mock_get.side_effect = requests.RequestException("Connection error")

        # Call the function
        success, content, error = fetch_url_content("https://example.com")

        # Assert results
        self.assertFalse(success)
        self.assertEqual(content, "")
        self.assertIsNotNone(error)
        if error:
            self.assertIn("Error fetching URL", error)
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


class SanitizeTextForTTSTests(TestCase):
    """Test text sanitization for TTS."""

    def test_empty_string(self):
        """Test sanitization of empty string."""
        self.assertEqual(sanitize_text_for_tts(""), "")

    def test_none_returns_empty(self):
        """Test sanitization of None returns empty string."""
        self.assertEqual(sanitize_text_for_tts(None), "")

    def test_plain_text_unchanged(self):
        """Test that plain text without URLs/markdown is unchanged."""
        text = "Hello world. This is a simple sentence."
        result = sanitize_text_for_tts(text)
        self.assertEqual(result, text)

    def test_removes_raw_urls(self):
        """Test removal of raw HTTP/HTTPS URLs."""
        text = "Check out https://example.com/page for more info."
        result = sanitize_text_for_tts(text)
        self.assertNotIn("https://", result)
        self.assertIn("Check out", result)
        self.assertIn("for more info", result)

    def test_removes_markdown_image_syntax(self):
        """Test removal of markdown image syntax ![alt](url)."""
        text = "Here is an image: ![alt text](https://example.com/img.jpg) in the text."
        result = sanitize_text_for_tts(text)
        self.assertNotIn("![", result)
        self.assertNotIn("example.com", result)
        self.assertIn("Here is an image:", result)

    def test_preserves_link_text_from_markdown(self):
        """Test that markdown link text is preserved while URL is removed."""
        text = "Click [this link](https://example.com) for more."
        result = sanitize_text_for_tts(text)
        self.assertIn("this link", result)
        self.assertNotIn("example.com", result)

    def test_removes_angle_bracket_urls(self):
        """Test removal of angle-bracket style URLs <http://...>."""
        text = "Visit <https://example.com/page> for details."
        result = sanitize_text_for_tts(text)
        self.assertNotIn("<https://", result)
        self.assertNotIn("example.com", result)

    def test_removes_bare_bracket_urls(self):
        """Test removal of bare URLs in brackets [https://...]."""
        text = "See [https://example.com/long/url/path] for info."
        result = sanitize_text_for_tts(text)
        self.assertNotIn("[https://", result)
        self.assertNotIn("example.com", result)

    def test_removes_email_addresses(self):
        """Test removal of email addresses."""
        text = "Contact us at support@example.com for help."
        result = sanitize_text_for_tts(text)
        self.assertNotIn("support@example.com", result)
        self.assertIn("Contact us at", result)

    def test_removes_html_tags(self):
        """Test removal of remaining HTML tags."""
        text = "Hello <b>world</b> with <a href='test'>link</a>."
        result = sanitize_text_for_tts(text)
        self.assertNotIn("<b>", result)
        self.assertNotIn("</b>", result)
        self.assertNotIn("<a", result)

    def test_normalizes_whitespace(self):
        """Test that multiple spaces are normalized to single space."""
        text = "Hello    world   with   spaces."
        result = sanitize_text_for_tts(text)
        self.assertNotIn("    ", result)
        self.assertEqual(result, "Hello world with spaces.")

    def test_normalizes_newlines(self):
        """Test that multiple newlines are reduced to max 2."""
        text = "Paragraph 1\n\n\n\n\nParagraph 2"
        result = sanitize_text_for_tts(text)
        self.assertNotIn("\n\n\n", result)

    def test_removes_empty_parentheses(self):
        """Test removal of empty parentheses that may remain after URL removal."""
        text = "See the link () for more."
        result = sanitize_text_for_tts(text)
        self.assertNotIn("()", result)

    def test_removes_empty_brackets(self):
        """Test removal of empty brackets that may remain after URL removal."""
        text = "See the link [] for more."
        result = sanitize_text_for_tts(text)
        self.assertNotIn("[]", result)

    def test_substack_style_content(self):
        """Test sanitization of Substack-style newsletter content.

        This is the specific pattern that caused the original error.
        """
        text = (
            "[https://substackcdn.com/image/fetch/w_36,c_scale,f_png/path]"
            "<https://substack.com/app-link/post?token=xyz>"
            " Some actual content here."
        )
        result = sanitize_text_for_tts(text)
        self.assertNotIn("substackcdn.com", result)
        self.assertNotIn("substack.com", result)
        self.assertIn("Some actual content here", result)

    def test_complex_newsletter_content(self):
        """Test sanitization of complex newsletter with multiple URL patterns."""
        text = """
        Welcome to the newsletter!

        [Image: Header](https://cdn.example.com/header.jpg)

        Here's today's article. Check out <https://example.com/article> for more.

        Contact: editor@newsletter.com

        [https://tracking.example.com/pixel.gif]

        Thanks for reading!
        """
        result = sanitize_text_for_tts(text)

        # Check URLs are removed
        self.assertNotIn("cdn.example.com", result)
        self.assertNotIn("example.com", result)
        self.assertNotIn("tracking.example.com", result)
        self.assertNotIn("editor@newsletter.com", result)

        # Check content is preserved
        self.assertIn("Welcome to the newsletter", result)
        self.assertIn("Here's today's article", result)
        self.assertIn("Thanks for reading", result)


if __name__ == "__main__":
    unittest.main()
