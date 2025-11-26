"""Tests for file upload handling - plaintext and markdown support."""

import base64
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings

from text_to_audio.forms import ArticleSubmissionForm
from text_to_audio.models import Article, Feed
from text_to_audio.tasks import process_incoming_email

User = get_user_model()


class ArticleSubmissionFormFileValidationTestCase(TestCase):
    """Tests for ArticleSubmissionForm file type validation."""

    def setUp(self):
        """Set up test fixtures."""
        self.user = User.objects.create_user(
            username="testuser",
            email="test@example.com",
            password="testpass123",
        )

    def _create_form_with_file(self, filename, content, content_type):
        """Helper to create a form with a file upload."""
        uploaded_file = SimpleUploadedFile(filename, content, content_type=content_type)
        return ArticleSubmissionForm(
            data={},
            files={"document_file": uploaded_file},
            user=self.user,
        )

    def test_form_accepts_plaintext_file(self):
        """Form should accept text/plain MIME type (.txt files)."""
        form = self._create_form_with_file(
            "article.txt",
            b"This is plain text content.",
            "text/plain",
        )
        # Form should not have file type validation error
        form.is_valid()
        errors = form.errors.get("__all__", [])
        file_type_errors = [e for e in errors if "Invalid file type" in str(e)]
        self.assertEqual(len(file_type_errors), 0)

    def test_form_accepts_markdown_file(self):
        """Form should accept text/markdown MIME type (.md files)."""
        form = self._create_form_with_file(
            "article.md",
            b"# Heading\n\nThis is markdown content.",
            "text/markdown",
        )
        form.is_valid()
        errors = form.errors.get("__all__", [])
        file_type_errors = [e for e in errors if "Invalid file type" in str(e)]
        self.assertEqual(len(file_type_errors), 0)

    def test_form_accepts_x_markdown_file(self):
        """Form should accept text/x-markdown MIME type (alternate markdown)."""
        form = self._create_form_with_file(
            "article.md",
            b"# Heading\n\nThis is markdown content.",
            "text/x-markdown",
        )
        form.is_valid()
        errors = form.errors.get("__all__", [])
        file_type_errors = [e for e in errors if "Invalid file type" in str(e)]
        self.assertEqual(len(file_type_errors), 0)

    def test_form_rejects_unsupported_file_type(self):
        """Form should reject unsupported file types."""
        form = self._create_form_with_file(
            "image.png",
            b"\x89PNG\r\n\x1a\n",  # PNG header
            "image/png",
        )
        self.assertFalse(form.is_valid())
        errors = form.errors.get("__all__", [])
        file_type_errors = [e for e in errors if "Invalid file type" in str(e)]
        self.assertEqual(len(file_type_errors), 1)


class ArticleSubmissionViewFileUploadTestCase(TestCase):
    """Tests for article submission view file upload handling."""

    def setUp(self):
        """Set up test fixtures."""
        self.client = Client()
        self.user = User.objects.create_user(
            username="testuser",
            email="test@example.com",
            password="testpass123",
        )
        self.feed = Feed.objects.create(
            user=self.user,
            name="Test Feed",
        )
        self.client.login(username="testuser", password="testpass123")

    @patch("text_to_audio.views.process_article.delay")
    def test_upload_plaintext_file_creates_article(self, mock_delay):
        """Uploading a .txt file should create an article with its content."""
        mock_task = MagicMock()
        mock_task.id = "mock-task-id"
        mock_delay.return_value = mock_task

        txt_content = (
            b"This is the content of my article.\n\nIt has multiple paragraphs."
        )
        txt_file = SimpleUploadedFile(
            "my-article.txt",
            txt_content,
            content_type="text/plain",
        )

        response = self.client.post(
            f"/feeds/{self.feed.pk}/add/",
            {"document_file": txt_file},
            format="multipart",
        )

        self.assertEqual(response.status_code, 302)
        article = Article.objects.get(feed=self.feed)
        self.assertEqual(
            article.text_content,
            "This is the content of my article.\n\nIt has multiple paragraphs.",
        )
        # Title should be derived from filename
        self.assertEqual(article.title, "my-article")

    @patch("text_to_audio.views.process_article.delay")
    def test_upload_markdown_file_creates_article(self, mock_delay):
        """Uploading a .md file should create an article with its content."""
        mock_task = MagicMock()
        mock_task.id = "mock-task-id"
        mock_delay.return_value = mock_task

        md_content = (
            b"# My Article Title\n\n## Introduction\n\nThis is markdown content."
        )
        md_file = SimpleUploadedFile(
            "my-article.md",
            md_content,
            content_type="text/markdown",
        )

        response = self.client.post(
            f"/feeds/{self.feed.pk}/add/",
            {"document_file": md_file},
            format="multipart",
        )

        self.assertEqual(response.status_code, 302)
        article = Article.objects.get(feed=self.feed)
        self.assertEqual(
            article.text_content,
            "# My Article Title\n\n## Introduction\n\nThis is markdown content.",
        )
        self.assertEqual(article.title, "my-article")

    @patch("text_to_audio.views.process_article.delay")
    def test_upload_empty_text_file_shows_error(self, mock_delay):
        """Uploading an empty text file should show an error."""
        txt_file = SimpleUploadedFile(
            "empty.txt",
            b"   \n\n  ",  # Only whitespace
            content_type="text/plain",
        )

        response = self.client.post(
            f"/feeds/{self.feed.pk}/add/",
            {"document_file": txt_file},
            format="multipart",
        )

        self.assertEqual(response.status_code, 200)  # Re-renders form with error
        self.assertContains(response, "file appears to be empty")
        self.assertEqual(Article.objects.count(), 0)

    @patch("text_to_audio.views.process_article.delay")
    def test_upload_text_file_with_title_provided(self, mock_delay):
        """When title is provided, it should be used instead of filename."""
        mock_task = MagicMock()
        mock_task.id = "mock-task-id"
        mock_delay.return_value = mock_task

        txt_file = SimpleUploadedFile(
            "random-filename.txt",
            b"Article content here.",
            content_type="text/plain",
        )

        response = self.client.post(
            f"/feeds/{self.feed.pk}/add/",
            {"document_file": txt_file, "title": "My Custom Title"},
            format="multipart",
        )

        self.assertEqual(response.status_code, 302)
        article = Article.objects.get(feed=self.feed)
        self.assertEqual(article.title, "My Custom Title")


class ProcessIncomingEmailTextAttachmentTestCase(TestCase):
    """Tests for processing email attachments with plaintext and markdown files."""

    def setUp(self):
        """Set up test fixtures."""
        self.user = User.objects.create_user(
            username="testuser",
            email="test@example.com",
            password="testpass123",
        )
        self.feed = Feed.objects.create(
            user=self.user,
            name="Test Feed",
            inbound_email="test-feed@mg.example.com",
        )

    @patch("text_to_audio.tasks.process_article.delay")
    @override_settings(ENABLE_EMAIL_CONTENT_CLEANING=False)
    def test_task_processes_plaintext_attachment(self, mock_process_article):
        """Task should extract content from plaintext attachments."""
        mock_process_article.return_value = MagicMock(id="task-123")

        txt_content = b"This is the article content from the text file."
        txt_b64 = base64.b64encode(txt_content).decode("ascii")

        payload = {
            "feed_id": self.feed.id,
            "subject": "Email Article",
            "text_content": "Fallback email body.",
            "sender": "sender@example.com",
            "attachments": [
                {
                    "filename": "article.txt",
                    "content_type": "text/plain",
                    "data": txt_b64,
                }
            ],
        }

        result = process_incoming_email(payload)

        self.assertIn("created successfully", result)

        # Verify article used attachment content, not email body
        article = Article.objects.get(feed=self.feed)
        self.assertEqual(
            article.text_content,
            "This is the article content from the text file.",
        )
        # Title should be derived from filename
        self.assertEqual(article.title, "article")

    @patch("text_to_audio.tasks.process_article.delay")
    @override_settings(ENABLE_EMAIL_CONTENT_CLEANING=False)
    def test_task_processes_markdown_attachment(self, mock_process_article):
        """Task should extract content from markdown attachments."""
        mock_process_article.return_value = MagicMock(id="task-123")

        md_content = b"# Article Title\n\nThis is markdown content."
        md_b64 = base64.b64encode(md_content).decode("ascii")

        payload = {
            "feed_id": self.feed.id,
            "subject": "Email Article",
            "text_content": "Fallback email body.",
            "sender": "sender@example.com",
            "attachments": [
                {
                    "filename": "article.md",
                    "content_type": "text/markdown",
                    "data": md_b64,
                }
            ],
        }

        result = process_incoming_email(payload)

        self.assertIn("created successfully", result)

        article = Article.objects.get(feed=self.feed)
        self.assertEqual(
            article.text_content,
            "# Article Title\n\nThis is markdown content.",
        )
        self.assertEqual(article.title, "article")

    @patch("text_to_audio.tasks.process_article.delay")
    @override_settings(ENABLE_EMAIL_CONTENT_CLEANING=False)
    def test_task_processes_x_markdown_attachment(self, mock_process_article):
        """Task should extract content from text/x-markdown attachments."""
        mock_process_article.return_value = MagicMock(id="task-123")

        md_content = b"# Article\n\nContent here."
        md_b64 = base64.b64encode(md_content).decode("ascii")

        payload = {
            "feed_id": self.feed.id,
            "subject": "Email Article",
            "text_content": "Fallback email body.",
            "sender": "sender@example.com",
            "attachments": [
                {
                    "filename": "readme.md",
                    "content_type": "text/x-markdown",
                    "data": md_b64,
                }
            ],
        }

        result = process_incoming_email(payload)

        self.assertIn("created successfully", result)

        article = Article.objects.get(feed=self.feed)
        self.assertEqual(article.text_content, "# Article\n\nContent here.")
        self.assertEqual(article.title, "readme")

    @patch("text_to_audio.tasks.process_article.delay")
    @override_settings(ENABLE_EMAIL_CONTENT_CLEANING=False)
    def test_task_skips_empty_text_attachment(self, mock_process_article):
        """Task should skip empty text attachments and fall back to email body."""
        mock_process_article.return_value = MagicMock(id="task-123")

        txt_b64 = base64.b64encode(b"   \n\n  ").decode("ascii")

        payload = {
            "feed_id": self.feed.id,
            "subject": "Test Subject",
            "text_content": "Email body content.",
            "sender": "sender@example.com",
            "attachments": [
                {
                    "filename": "empty.txt",
                    "content_type": "text/plain",
                    "data": txt_b64,
                }
            ],
        }

        result = process_incoming_email(payload)

        self.assertIn("created successfully", result)

        # Should use email body since attachment was empty
        article = Article.objects.get(feed=self.feed)
        self.assertEqual(article.text_content, "Email body content.")
        self.assertEqual(article.title, "Test Subject")
