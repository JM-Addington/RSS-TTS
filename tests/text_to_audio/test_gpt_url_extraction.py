"""Tests for GPT-based URL extraction functionality."""

from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings

from text_to_audio.utils import (
    clean_html_minimal,
    extract_article_text_with_gpt,
    process_url_to_text,
)


class GptUrlExtractionTests(TestCase):
    """Test GPT-based URL extraction functionality."""

    def test_clean_html_minimal_removes_scripts_and_styles(self):
        """Test that clean_html_minimal removes script and style tags."""
        html = """
        <html>
            <head>
                <style>body { color: red; }</style>
                <script>alert('test');</script>
            </head>
            <body>
                <h1>Test Article</h1>
                <p>This is content.</p>
                <script>console.log('another script');</script>
            </body>
        </html>
        """

        cleaned = clean_html_minimal(html)

        # Should not contain script or style tags
        self.assertNotIn("<script", cleaned)
        self.assertNotIn("<style", cleaned)
        self.assertNotIn("alert(", cleaned)
        self.assertNotIn("console.log", cleaned)
        self.assertNotIn("color: red", cleaned)

        # Should still contain content
        self.assertIn("Test Article", cleaned)
        self.assertIn("This is content.", cleaned)

    def test_clean_html_minimal_removes_unwanted_attributes(self):
        """Test that clean_html_minimal removes class, id, and style attributes."""
        html = """
        <div class="container" id="main" style="margin: 10px;">
            <h1 class="title" id="article-title">Test Article</h1>
            <p class="paragraph" onclick="doSomething()">Content here.</p>
            <a href="/link" class="link-class">Keep href</a>
            <img src="image.jpg" alt="Test image" class="img-class">
        </div>
        """

        cleaned = clean_html_minimal(html)

        # Should not contain class, id, style, or onclick attributes
        self.assertNotIn("class=", cleaned)
        self.assertNotIn("id=", cleaned)
        self.assertNotIn("style=", cleaned)
        self.assertNotIn("onclick=", cleaned)

        # Should keep href for links and src/alt for images
        self.assertIn('href="/link"', cleaned)
        self.assertIn('src="image.jpg"', cleaned)
        self.assertIn('alt="Test image"', cleaned)

    def test_clean_html_minimal_removes_form_elements(self):
        """Test that clean_html_minimal removes form-related elements."""
        html = """
        <article>
            <h1>Article Title</h1>
            <form action="/submit">
                <input type="text" name="email">
                <button type="submit">Subscribe</button>
            </form>
            <p>Article content here.</p>
        </article>
        """

        cleaned = clean_html_minimal(html)

        # Should not contain form elements
        self.assertNotIn("<form", cleaned)
        self.assertNotIn("<input", cleaned)
        self.assertNotIn("<button", cleaned)

        # Should keep article content
        self.assertIn("Article Title", cleaned)
        self.assertIn("Article content here.", cleaned)

    @patch("openai.OpenAI")
    @override_settings(OPENAI_API_KEY="test-key")
    def test_extract_article_text_with_gpt_success(self, mock_openai_class):
        """Test successful GPT-based article extraction."""
        # Mock OpenAI client and response
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[
            0
        ].message.content = """
        Test Article Title

        This is the main article content that was extracted by GPT-4.1.
        It includes multiple paragraphs and maintains structure.

        [Image: A test image description]

        More content here.
        """
        mock_response.id = "test-response-id"
        mock_response.model = "gpt-4.1-2025-04-14"
        mock_response.object = "chat.completion"
        mock_response.created = 1234567890
        mock_response.choices[0].index = 0
        mock_response.choices[0].message.role = "assistant"
        mock_response.choices[0].finish_reason = "stop"
        mock_response.usage.prompt_tokens = 1000
        mock_response.usage.completion_tokens = 200
        mock_response.usage.total_tokens = 1200

        mock_client.chat.completions.create.return_value = mock_response

        # Test HTML
        html = """
        <html>
            <body>
                <nav>Navigation menu</nav>
                <article>
                    <h1>Test Article Title</h1>
                    <p>Article content</p>
                </article>
                <footer>Footer content</footer>
            </body>
        </html>
        """

        success, text, error = extract_article_text_with_gpt(
            html, "https://example.com"
        )

        # Verify success
        self.assertTrue(success)
        self.assertIsNone(error)
        self.assertIn("Test Article Title", text)
        self.assertIn("GPT-4.1", text)

        # Verify API was called with correct model
        call_args = mock_client.chat.completions.create.call_args
        self.assertEqual(call_args[1]["model"], "gpt-4.1-2025-04-14")
        self.assertEqual(call_args[1]["max_tokens"], 32768)
        self.assertEqual(call_args[1]["temperature"], 0.1)

    @patch("openai.OpenAI")
    @override_settings(OPENAI_API_KEY="test-key")
    def test_extract_article_text_with_gpt_api_error(self, mock_openai_class):
        """Test handling of OpenAI API errors."""
        # Mock OpenAI client to raise an error
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client

        # Use a generic exception since openai.APIError requires specific parameters
        mock_client.chat.completions.create.side_effect = Exception(
            "API rate limit exceeded"
        )

        html = "<html><body><p>Test</p></body></html>"

        success, text, error = extract_article_text_with_gpt(
            html, "https://example.com"
        )

        # Should fail gracefully
        self.assertFalse(success)
        self.assertEqual(text, "")
        self.assertIn("Error calling GPT-4.1", error)

    @patch("text_to_audio.utils.fetch_url_content")
    @patch("text_to_audio.utils.extract_article_text_with_gpt")
    @patch("text_to_audio.utils.extract_article_text")
    @override_settings(USE_GPT_FOR_URL_EXTRACTION=True)
    def test_process_url_to_text_uses_gpt_when_enabled(
        self, mock_traditional, mock_gpt, mock_fetch
    ):
        """Test that process_url_to_text uses GPT extraction when enabled."""
        # Mock successful URL fetch
        mock_fetch.return_value = (True, "<html><body>Test</body></html>", None)

        # Mock successful GPT extraction
        mock_gpt.return_value = (True, "GPT extracted content", None)

        # Process URL
        success, text, error = process_url_to_text("https://example.com")

        # Should use GPT extraction
        self.assertTrue(success)
        self.assertEqual(text, "GPT extracted content")
        self.assertIsNone(error)

        # GPT extraction should be called
        mock_gpt.assert_called_once()
        # Traditional extraction should NOT be called
        mock_traditional.assert_not_called()

    @patch("text_to_audio.utils.fetch_url_content")
    @patch("text_to_audio.utils.extract_article_text_with_gpt")
    @patch("text_to_audio.utils.extract_article_text")
    @override_settings(USE_GPT_FOR_URL_EXTRACTION=True)
    def test_process_url_to_text_falls_back_on_gpt_failure(
        self, mock_traditional, mock_gpt, mock_fetch
    ):
        """Test fallback to traditional extraction when GPT fails."""
        # Mock successful URL fetch
        mock_fetch.return_value = (True, "<html><body>Test</body></html>", None)

        # Mock failed GPT extraction
        mock_gpt.return_value = (False, "", "GPT extraction failed")

        # Mock successful traditional extraction
        mock_traditional.return_value = (True, "Traditional extracted content", None)

        # Process URL
        success, text, error = process_url_to_text("https://example.com")

        # Should fall back to traditional extraction
        self.assertTrue(success)
        self.assertEqual(text, "Traditional extracted content")
        self.assertIsNone(error)

        # Both extraction methods should be called
        mock_gpt.assert_called_once()
        mock_traditional.assert_called_once()

    @patch("text_to_audio.utils.fetch_url_content")
    @patch("text_to_audio.utils.extract_article_text_with_gpt")
    @patch("text_to_audio.utils.extract_article_text")
    @override_settings(USE_GPT_FOR_URL_EXTRACTION=False)
    def test_process_url_to_text_skips_gpt_when_disabled(
        self, mock_traditional, mock_gpt, mock_fetch
    ):
        """Test that GPT extraction is skipped when disabled."""
        # Mock successful URL fetch
        mock_fetch.return_value = (True, "<html><body>Test</body></html>", None)

        # Mock successful traditional extraction
        mock_traditional.return_value = (True, "Traditional extracted content", None)

        # Process URL
        success, text, error = process_url_to_text("https://example.com")

        # Should use traditional extraction
        self.assertTrue(success)
        self.assertEqual(text, "Traditional extracted content")
        self.assertIsNone(error)

        # GPT extraction should NOT be called
        mock_gpt.assert_not_called()
        # Traditional extraction should be called
        mock_traditional.assert_called_once()
