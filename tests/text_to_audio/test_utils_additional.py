# flake8: noqa
# mypy: ignore-errors
"""Additional utility function tests."""

from unittest.mock import patch

from django.test import TestCase

from bs4 import BeautifulSoup

from text_to_audio.utils import (
    _extract_image_descriptions,
    _extract_table_captions,
    _extract_text_elements,
    _find_main_container,
    _handle_http_error,
    _handle_retry,
    extract_title_from_html,
)


class UtilsHelperFunctionTests(TestCase):
    """Tests for additional utility helper functions."""

    def test_extract_title_from_html(self):
        """Title is extracted when present."""
        html = "<html><head><title>My Page</title></head></html>"
        self.assertEqual(extract_title_from_html(html), "My Page")

    def test_extract_title_from_html_missing(self):
        """Returns empty string when title missing."""
        self.assertEqual(extract_title_from_html("<html></html>"), "")

    def test_handle_http_error_404(self):
        """404 error returns formatted tuple."""
        result = _handle_http_error(404, "http://example.com")
        self.assertEqual(
            result,
            (
                False,
                "",
                (
                    "404 Not Found: The requested page 'http://example.com' "
                    "could not be found."
                ),
            ),
        )

    def test_handle_http_error_500_returns_none(self):
        """500 error triggers retry (None)."""
        self.assertIsNone(_handle_http_error(500, "http://example.com"))

    def test_handle_http_error_200_returns_none(self):
        """200 status returns None."""
        self.assertIsNone(_handle_http_error(200, "http://example.com"))

    @patch("text_to_audio.utils.time.sleep")
    def test_handle_retry_exponential_backoff(self, mock_sleep):
        """Retry sleeps with exponential backoff."""
        _handle_retry(1, 3, "http://example.com", "Timeout")
        mock_sleep.assert_called_once_with(2**1)

    def test_find_main_container_article_preferred(self):
        """Article tag is preferred as main container."""
        html = "<html><body><article><p>text</p></article></body></html>"
        soup = BeautifulSoup(html, "html.parser")
        container = _find_main_container(soup)
        self.assertIsNotNone(container)
        assert container is not None
        self.assertEqual(container.name, "article")

    def test_extract_text_elements(self):
        """Extracts headings, paragraphs and list items."""
        html = "<div><h1>Title</h1><p>Para</p><li>Item</li></div>"
        soup = BeautifulSoup(html, "html.parser")
        result = _extract_text_elements(soup.div)
        self.assertEqual(result, ["Title", "Para", "Item"])

    def test_extract_image_descriptions(self):
        """Extracts image alt descriptions."""
        html = '<div><img src="a.jpg" alt="desc"></div>'
        soup = BeautifulSoup(html, "html.parser")
        self.assertEqual(_extract_image_descriptions(soup.div), ["[Image: desc]"])

    def test_extract_table_captions(self):
        """Extracts table captions."""
        html = "<div><table><caption>Cap</caption></table></div>"
        soup = BeautifulSoup(html, "html.parser")
        self.assertEqual(_extract_table_captions(soup.div), ["[Table: Cap]"])
