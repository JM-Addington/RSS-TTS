"""Tests for file processing functionality."""

import io
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from text_to_audio.services.file_processing import FileProcessingService


class TestFileProcessingService(TestCase):
    """Test the FileProcessingService."""

    def setUp(self):
        """Set up the test."""
        self.service = FileProcessingService()

    def test_detect_file_type_pdf(self):
        """Test detection of PDF files."""
        # Test with PDF MIME type
        pdf_file = SimpleUploadedFile("test.pdf", b"content", content_type="application/pdf")
        self.assertEqual(self.service.detect_file_type(pdf_file), "pdf")

        # Test with PDF extension
        pdf_file = SimpleUploadedFile("test.PDF", b"content")
        self.assertEqual(self.service.detect_file_type(pdf_file), "pdf")

    def test_detect_file_type_html(self):
        """Test detection of HTML files."""
        # Test with HTML MIME type
        html_file = SimpleUploadedFile("test.html", b"content", content_type="text/html")
        self.assertEqual(self.service.detect_file_type(html_file), "html")

        # Test with HTML extension
        html_file = SimpleUploadedFile("test.HTM", b"content")
        self.assertEqual(self.service.detect_file_type(html_file), "html")

    def test_detect_file_type_txt(self):
        """Test detection of text files."""
        # Test with text MIME type
        txt_file = SimpleUploadedFile("test.txt", b"content", content_type="text/plain")
        self.assertEqual(self.service.detect_file_type(txt_file), "txt")

        # Test with TXT extension
        txt_file = SimpleUploadedFile("test.TXT", b"content")
        self.assertEqual(self.service.detect_file_type(txt_file), "txt")

    def test_detect_file_type_unsupported(self):
        """Test detection of unsupported files."""
        unsupported_file = SimpleUploadedFile("test.doc", b"content")
        self.assertIsNone(self.service.detect_file_type(unsupported_file))

    def test_extract_text_from_txt(self):
        """Test text extraction from plain text files."""
        content = "This is a test document.\nWith multiple lines."
        content_bytes = content.encode("utf-8")

        success, extracted_text, error = self.service.extract_text_from_txt(content_bytes)

        self.assertTrue(success)
        self.assertEqual(extracted_text, content)
        self.assertIsNone(error)

    def test_extract_text_from_txt_empty(self):
        """Test text extraction from empty text file."""
        content_bytes = b""

        success, extracted_text, error = self.service.extract_text_from_txt(content_bytes)

        self.assertFalse(success)
        self.assertEqual(extracted_text, "")
        self.assertIn("empty", error)

    def test_extract_text_from_html(self):
        """Test text extraction from HTML files."""
        html_content = """
        <html>
        <head><title>Test Title</title></head>
        <body>
            <h1>Main Heading</h1>
            <p>This is a paragraph.</p>
            <p>Another paragraph.</p>
        </body>
        </html>
        """
        content_bytes = html_content.encode("utf-8")

        success, extracted_text, error = self.service.extract_text_from_html(content_bytes)

        self.assertTrue(success)
        self.assertIn("Main Heading", extracted_text)
        self.assertIn("This is a paragraph", extracted_text)
        self.assertIsNone(error)

    @patch('builtins.__import__')
    def test_extract_text_from_pdf_success(self, mock_import):
        """Test successful PDF text extraction."""
        # Mock PyPDF2 import and components
        mock_page = MagicMock()
        mock_page.extract_text.return_value = "This is text from a PDF page."

        mock_reader = MagicMock()
        mock_reader.pages = [mock_page]

        mock_pypdf2 = MagicMock()
        mock_pypdf2.PdfReader.return_value = mock_reader

        def side_effect(name, *args, **kwargs):
            if name == 'PyPDF2':
                return mock_pypdf2
            return __import__(name, *args, **kwargs)

        mock_import.side_effect = side_effect

        content_bytes = b"fake_pdf_content"

        success, extracted_text, error = self.service.extract_text_from_pdf(content_bytes)

        self.assertTrue(success)
        self.assertEqual(extracted_text, "This is text from a PDF page.")
        self.assertIsNone(error)

    @patch('builtins.__import__')
    def test_extract_text_from_pdf_no_pypdf2(self, mock_import):
        """Test PDF extraction when PyPDF2 is not available."""
        def side_effect(name, *args, **kwargs):
            if name == 'PyPDF2':
                raise ImportError("PyPDF2 not available")
            return __import__(name, *args, **kwargs)

        mock_import.side_effect = side_effect

        content_bytes = b"fake_pdf_content"

        success, extracted_text, error = self.service.extract_text_from_pdf(content_bytes)

        self.assertFalse(success)
        self.assertEqual(extracted_text, "")
        self.assertIn("PyPDF2", error)

    def test_process_uploaded_file_txt(self):
        """Test processing of uploaded text file."""
        content = "This is a test document."
        txt_file = SimpleUploadedFile("test.txt", content.encode("utf-8"), content_type="text/plain")

        success, extracted_text, file_type, error = self.service.process_uploaded_file(txt_file)

        self.assertTrue(success)
        self.assertEqual(extracted_text, content)
        self.assertEqual(file_type, "txt")
        self.assertIsNone(error)

    def test_process_uploaded_file_unsupported(self):
        """Test processing of unsupported file type."""
        doc_file = SimpleUploadedFile("test.doc", b"content")

        success, extracted_text, file_type, error = self.service.process_uploaded_file(doc_file)

        self.assertFalse(success)
        self.assertEqual(extracted_text, "")
        self.assertEqual(file_type, "")
        self.assertIn("Unsupported file type", error)

    def test_process_uploaded_file_empty(self):
        """Test processing of empty file."""
        empty_file = SimpleUploadedFile("test.txt", b"", content_type="text/plain")

        success, extracted_text, file_type, error = self.service.process_uploaded_file(empty_file)

        self.assertFalse(success)
        self.assertEqual(extracted_text, "")
        self.assertEqual(file_type, "txt")
        self.assertIn("empty", error)

    def test_process_uploaded_file_too_large(self):
        """Test processing of file that exceeds size limit."""
        # Create a file larger than 50MB
        large_content = b"x" * (51 * 1024 * 1024)  # 51MB
        large_file = SimpleUploadedFile("test.txt", large_content, content_type="text/plain")

        success, extracted_text, file_type, error = self.service.process_uploaded_file(large_file)

        self.assertFalse(success)
        self.assertEqual(extracted_text, "")
        self.assertEqual(file_type, "txt")
        self.assertIn("too large", error)

    @patch('text_to_audio.services.file_processing.openai.OpenAI')
    @patch('django.conf.settings')
    def test_process_file_with_gpt_success(self, mock_settings, mock_openai_class):
        """Test GPT-based file processing."""
        # Mock settings
        mock_settings.OPENAI_API_KEY = 'test-key'

        # Mock OpenAI response
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Cleaned and structured text content."
        mock_response.usage = MagicMock()
        mock_response.usage.prompt_tokens = 100
        mock_response.usage.completion_tokens = 50
        mock_response.usage.total_tokens = 150
        mock_response.id = "test-id"
        mock_response.model = "gpt-4.1-2025-04-14"
        mock_response.object = "chat.completion"
        mock_response.created = 1234567890

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai_class.return_value = mock_client

        content = "Raw text content from file."
        content_bytes = content.encode("utf-8")

        success, cleaned_text, error = self.service.process_file_with_gpt(
            content_bytes, "txt", "test.txt"
        )

        self.assertTrue(success)
        self.assertEqual(cleaned_text, "Cleaned and structured text content.")
        self.assertIsNone(error)

    @patch('text_to_audio.services.file_processing.openai.OpenAI')
    @patch('django.conf.settings')
    def test_process_file_with_gpt_api_error(self, mock_settings, mock_openai_class):
        """Test GPT processing with API error fallback."""
        # Mock settings
        mock_settings.OPENAI_API_KEY = 'test-key'

        # Mock OpenAI API error
        import openai
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = openai.APIError("API Error", request=None, body=None)
        mock_openai_class.return_value = mock_client

        content = "Raw text content from file."
        content_bytes = content.encode("utf-8")

        success, extracted_text, error = self.service.process_file_with_gpt(
            content_bytes, "txt", "test.txt"
        )

        # Should fall back to raw extracted text
        self.assertTrue(success)
        self.assertEqual(extracted_text, content)
        self.assertIsNone(error)

    @patch('django.conf.settings')
    def test_process_uploaded_file_without_gpt(self, mock_settings):
        """Test file processing with GPT disabled."""
        # Mock settings
        mock_settings.USE_GPT_FOR_FILE_PROCESSING = False

        content = "This is a test document."
        txt_file = SimpleUploadedFile("test.txt", content.encode("utf-8"), content_type="text/plain")

        success, extracted_text, file_type, error = self.service.process_uploaded_file(txt_file)

        self.assertTrue(success)
        self.assertEqual(extracted_text, content)
        self.assertEqual(file_type, "txt")
        self.assertIsNone(error)


if __name__ == '__main__':
    unittest.main()
