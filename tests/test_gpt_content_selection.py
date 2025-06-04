"""Tests for GPT-powered content selection functionality."""

import json
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from text_to_audio.models import Article, Feed
from text_to_audio.services.content_selection import ContentSelectionService
from text_to_audio.utils import extract_article_text_with_gpt, process_url_to_text

User = get_user_model()


class ContentSelectionServiceTests(TestCase):
    """Test the ContentSelectionService class."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass123"
        )
        self.feed = Feed.objects.create(user=self.user, name="Test Feed")
        self.article = Article.objects.create(
            feed=self.feed, title="Test Article", text_content="This is a test article."
        )

        # Sample HTML with various content types
        self.sample_html = """
        <html>
            <head><title>Test Article</title></head>
            <body>
                <nav>Navigation menu</nav>
                <div class="ads">Advertisement content</div>
                <article>
                    <h1>Main Article Title</h1>
                    <p>This is the main article content that should be extracted.</p>
                    <p>This is another paragraph with important information.</p>
                    <blockquote>This is an important quote.</blockquote>
                </article>
                <aside>Sidebar content</aside>
                <footer>Footer content</footer>
            </body>
        </html>
        """

        self.expected_content = """Main Article Title

This is the main article content that should be extracted.

This is another paragraph with important information.

"This is an important quote.\""""

    @patch("openai.OpenAI")
    def test_extract_content_with_gpt_success(self, mock_openai_class):
        """Test successful content extraction with GPT."""
        # Mock OpenAI response
        mock_response = Mock()
        mock_response.id = "test-response-id"
        mock_response.model = "gpt-4.1"
        mock_response.choices = [
            Mock(
                message=Mock(
                    content=json.dumps({"extracted_content": self.expected_content})
                )
            )
        ]
        mock_response.usage = Mock(
            prompt_tokens=1000, completion_tokens=200, total_tokens=1200
        )

        mock_client = Mock()
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai_class.return_value = mock_client

        # Test the service
        service = ContentSelectionService()
        success, content, error = service.extract_content_with_gpt(
            self.sample_html, "https://example.com/test"
        )

        self.assertTrue(success)
        self.assertEqual(content, self.expected_content)
        self.assertIsNone(error)

        # Verify OpenAI was called correctly
        mock_client.chat.completions.create.assert_called_once()
        call_args = mock_client.chat.completions.create.call_args[1]
        self.assertEqual(call_args["model"], "gpt-4.1")
        self.assertEqual(call_args["temperature"], 0.1)
        self.assertEqual(call_args["response_format"], {"type": "json_object"})

    @patch("openai.OpenAI")
    def test_extract_content_with_gpt_invalid_json(self, mock_openai_class):
        """Test handling of invalid JSON response."""
        # Mock OpenAI response with invalid JSON
        mock_response = Mock()
        mock_response.choices = [Mock(message=Mock(content="invalid json content"))]

        mock_client = Mock()
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai_class.return_value = mock_client

        service = ContentSelectionService()
        success, content, error = service.extract_content_with_gpt(
            self.sample_html, "https://example.com/test"
        )

        self.assertFalse(success)
        self.assertEqual(content, "")
        self.assertIn("Failed to parse GPT response", error)

    @patch("openai.OpenAI")
    def test_extract_content_with_gpt_missing_key(self, mock_openai_class):
        """Test handling of response missing expected key."""
        # Mock OpenAI response missing 'extracted_content' key
        mock_response = Mock()
        mock_response.choices = [
            Mock(message=Mock(content=json.dumps({"wrong_key": "some content"})))
        ]

        mock_client = Mock()
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai_class.return_value = mock_client

        service = ContentSelectionService()
        success, content, error = service.extract_content_with_gpt(
            self.sample_html, "https://example.com/test"
        )

        self.assertFalse(success)
        self.assertEqual(content, "")
        self.assertIn("Missing 'extracted_content'", error)

    @patch("openai.OpenAI")
    def test_extract_content_with_gpt_api_error(self, mock_openai_class):
        """Test handling of OpenAI API errors."""
        # Mock OpenAI API error
        mock_client = Mock()
        mock_client.chat.completions.create.side_effect = Exception("API Error")
        mock_openai_class.return_value = mock_client

        service = ContentSelectionService()
        success, content, error = service.extract_content_with_gpt(
            self.sample_html, "https://example.com/test"
        )

        self.assertFalse(success)
        self.assertEqual(content, "")
        self.assertIn("Error in GPT content selection", error)

    def test_truncate_html_if_needed(self):
        """Test HTML truncation for large content."""
        service = ContentSelectionService()

        # Test content under limit
        small_html = "<html><body>Small content</body></html>"
        result = service._truncate_html_if_needed(small_html, "test.com")
        self.assertEqual(result, small_html)

        # Test content over limit
        large_html = "x" * 60000  # Larger than MAX_HTML_ANALYSIS_LENGTH
        result = service._truncate_html_if_needed(large_html, "test.com")
        self.assertLess(len(result), 60000)
        self.assertLessEqual(len(result), 50000)  # Should be truncated to limit

    @patch("openai.OpenAI")
    def test_usage_logger_integration(self, mock_openai_class):
        """Test that usage logger is called when provided."""
        # Mock successful response
        mock_response = Mock()
        mock_response.id = "test-id"
        mock_response.model = "gpt-4.1"
        mock_response.choices = [
            Mock(
                message=Mock(content=json.dumps({"extracted_content": "Test content"}))
            )
        ]
        mock_response.usage = Mock(
            prompt_tokens=500, completion_tokens=100, total_tokens=600
        )

        mock_client = Mock()
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai_class.return_value = mock_client

        # Mock usage logger
        mock_usage_logger = Mock()

        service = ContentSelectionService(usage_logger=mock_usage_logger)
        success, content, error = service.extract_content_with_gpt(
            self.sample_html, "https://example.com/test"
        )

        self.assertTrue(success)

        # Verify usage logger was called
        mock_usage_logger.log_llm_usage.assert_called_once()
        call_args = mock_usage_logger.log_llm_usage.call_args[1]
        self.assertEqual(call_args["operation"], "Content Selection")
        self.assertEqual(call_args["tokens_used"], 600)
        self.assertEqual(call_args["model_name"], "gpt-4.1")
        self.assertEqual(call_args["input_tokens"], 500)
        self.assertEqual(call_args["output_tokens"], 100)


class ExtractArticleTextWithGPTTests(TestCase):
    """Test the extract_article_text_with_gpt function."""

    def setUp(self):
        """Set up test data."""
        self.sample_html = """
        <html>
            <body>
                <article>
                    <h1>Test Article</h1>
                    <p>This is test content.</p>
                </article>
            </body>
        </html>
        """

    @override_settings(ENABLE_GPT_CONTENT_SELECTION=False)
    def test_gpt_selection_disabled(self):
        """Test fallback to basic extraction when GPT selection is disabled."""
        with patch("text_to_audio.utils.extract_article_text") as mock_basic:
            mock_basic.return_value = (True, "Basic extracted content", None)

            success, content, error = extract_article_text_with_gpt(
                self.sample_html, "https://example.com/test"
            )

            self.assertTrue(success)
            self.assertEqual(content, "Basic extracted content")
            mock_basic.assert_called_once_with(self.sample_html)

    @override_settings(OPENAI_API_KEY=None)
    def test_no_api_key(self):
        """Test fallback to basic extraction when no API key is available."""
        with patch("text_to_audio.utils.extract_article_text") as mock_basic:
            mock_basic.return_value = (True, "Basic extracted content", None)

            success, content, error = extract_article_text_with_gpt(
                self.sample_html, "https://example.com/test"
            )

            self.assertTrue(success)
            self.assertEqual(content, "Basic extracted content")
            mock_basic.assert_called_once_with(self.sample_html)

    @override_settings(ENABLE_GPT_CONTENT_SELECTION=True, OPENAI_API_KEY="test-key")
    @patch("text_to_audio.services.content_selection.ContentSelectionService")
    def test_gpt_extraction_success(self, mock_service_class):
        """Test successful GPT extraction."""
        # Mock the service
        mock_service = Mock()
        mock_service.extract_content_with_gpt.return_value = (
            True,
            "GPT extracted content",
            None,
        )
        mock_service_class.return_value = mock_service

        success, content, error = extract_article_text_with_gpt(
            self.sample_html, "https://example.com/test"
        )

        self.assertTrue(success)
        self.assertEqual(content, "GPT extracted content")
        self.assertIsNone(error)

        # Verify service was called correctly
        mock_service.extract_content_with_gpt.assert_called_once_with(
            self.sample_html, "https://example.com/test"
        )

    @override_settings(ENABLE_GPT_CONTENT_SELECTION=True, OPENAI_API_KEY="test-key")
    @patch("text_to_audio.services.content_selection.ContentSelectionService")
    @patch("text_to_audio.utils.extract_article_text")
    def test_gpt_extraction_fallback(self, mock_basic, mock_service_class):
        """Test fallback to basic extraction when GPT fails."""
        # Mock GPT service failure
        mock_service = Mock()
        mock_service.extract_content_with_gpt.return_value = (False, "", "GPT error")
        mock_service_class.return_value = mock_service

        # Mock successful basic extraction
        mock_basic.return_value = (True, "Basic fallback content", None)

        success, content, error = extract_article_text_with_gpt(
            self.sample_html, "https://example.com/test"
        )

        self.assertTrue(success)
        self.assertEqual(content, "Basic fallback content")

        # Verify both methods were called
        mock_service.extract_content_with_gpt.assert_called_once()
        mock_basic.assert_called_once_with(self.sample_html)


class ProcessUrlToTextIntegrationTests(TestCase):
    """Integration tests for the enhanced process_url_to_text function."""

    @patch("text_to_audio.utils.fetch_url_content")
    @patch("text_to_audio.utils.extract_article_text_with_gpt")
    def test_process_url_to_text_with_usage_logger(self, mock_extract, mock_fetch):
        """Test that process_url_to_text passes usage_logger correctly."""
        # Mock successful URL fetch
        mock_fetch.return_value = (True, "<html>content</html>", None)

        # Mock successful content extraction
        mock_extract.return_value = (True, "Extracted content", None)

        # Mock usage logger
        mock_usage_logger = Mock()

        success, content, error = process_url_to_text(
            "https://example.com/test", mock_usage_logger
        )

        self.assertTrue(success)
        self.assertEqual(content, "Extracted content")
        self.assertIsNone(error)

        # Verify functions were called correctly
        mock_fetch.assert_called_once_with("https://example.com/test")
        mock_extract.assert_called_once_with(
            "<html>content</html>", "https://example.com/test", mock_usage_logger
        )

    @patch("text_to_audio.utils.fetch_url_content")
    def test_process_url_to_text_fetch_failure(self, mock_fetch):
        """Test handling of URL fetch failures."""
        # Mock URL fetch failure
        mock_fetch.return_value = (False, "", "404 Not Found")

        success, content, error = process_url_to_text("https://example.com/test")

        self.assertFalse(success)
        self.assertEqual(content, "")
        self.assertEqual(error, "404 Not Found")

    @patch("text_to_audio.utils.fetch_url_content")
    @patch("text_to_audio.utils.extract_article_text_with_gpt")
    def test_process_url_to_text_extraction_failure(self, mock_extract, mock_fetch):
        """Test handling of content extraction failures."""
        # Mock successful URL fetch
        mock_fetch.return_value = (True, "<html>content</html>", None)

        # Mock extraction failure
        mock_extract.return_value = (False, "", "Extraction failed")

        success, content, error = process_url_to_text("https://example.com/test")

        self.assertFalse(success)
        self.assertEqual(content, "")
        self.assertEqual(error, "Extraction failed")


class GPTContentSelectionSettingsTests(TestCase):
    """Test settings integration for GPT content selection."""

    @override_settings(ENABLE_GPT_CONTENT_SELECTION=True)
    def test_gpt_selection_enabled_setting(self):
        """Test that GPT selection respects the enabled setting."""
        from django.conf import settings

        self.assertTrue(settings.ENABLE_GPT_CONTENT_SELECTION)

    @override_settings(ENABLE_GPT_CONTENT_SELECTION=False)
    def test_gpt_selection_disabled_setting(self):
        """Test that GPT selection respects the disabled setting."""
        from django.conf import settings

        self.assertFalse(settings.ENABLE_GPT_CONTENT_SELECTION)

    @override_settings(MAX_HTML_ANALYSIS_LENGTH=30000)
    def test_html_analysis_length_setting(self):
        """Test that HTML analysis length setting is respected."""
        from django.conf import settings

        self.assertEqual(settings.MAX_HTML_ANALYSIS_LENGTH, 30000)
