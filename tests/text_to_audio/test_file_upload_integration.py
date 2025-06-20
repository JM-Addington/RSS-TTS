"""Integration tests for file upload functionality."""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from text_to_audio.forms import ArticleSubmissionForm
from text_to_audio.models import Article, Feed

User = get_user_model()


class FileUploadFormTests(TestCase):
    """Test the ArticleSubmissionForm with file uploads."""

    def setUp(self):
        """Set up test user and form."""
        self.user = User.objects.create_user(
            username="testuser",
            email="test@example.com",
            password="testpass"
        )

    def test_form_validation_with_file(self):
        """Test form validation with uploaded file."""
        uploaded_file = SimpleUploadedFile(
            "test.txt",
            b"This is test content.",
            content_type="text/plain"
        )

        form_data = {
            'title': 'Test Article',
            'voice_id': '',
            'speed': '',
            'voice_preset': '',
        }

        form = ArticleSubmissionForm(
            data=form_data,
            files={'uploaded_file': uploaded_file},
            user=self.user
        )

        self.assertTrue(form.is_valid())

    def test_form_validation_multiple_inputs(self):
        """Test form validation fails with multiple input methods."""
        uploaded_file = SimpleUploadedFile(
            "test.txt",
            b"This is test content.",
            content_type="text/plain"
        )

        form_data = {
            'title': 'Test Article',
            'source_url': 'https://example.com/article',
            'text_content': 'Some text content',
            'voice_id': '',
            'speed': '',
            'voice_preset': '',
        }

        form = ArticleSubmissionForm(
            data=form_data,
            files={'uploaded_file': uploaded_file},
            user=self.user
        )

        self.assertFalse(form.is_valid())
        self.assertIn('only one input method', str(form.errors))

    def test_form_validation_no_input(self):
        """Test form validation fails with no input."""
        form_data = {
            'title': 'Test Article',
            'voice_id': '',
            'speed': '',
            'voice_preset': '',
        }

        form = ArticleSubmissionForm(data=form_data, user=self.user)

        self.assertFalse(form.is_valid())
        self.assertIn('must provide either', str(form.errors))

    def test_form_validation_unsupported_file_type(self):
        """Test form validation fails with unsupported file type."""
        uploaded_file = SimpleUploadedFile(
            "test.doc",
            b"This is a Word document.",
            content_type="application/msword"
        )

        form_data = {
            'title': 'Test Article',
            'voice_id': '',
            'speed': '',
            'voice_preset': '',
        }

        form = ArticleSubmissionForm(
            data=form_data,
            files={'uploaded_file': uploaded_file},
            user=self.user
        )

        self.assertFalse(form.is_valid())
        self.assertIn('Unsupported file type', str(form.errors))

    def test_form_validation_file_too_large(self):
        """Test form validation fails with file too large."""
        # Create a file larger than 50MB
        large_content = b"x" * (51 * 1024 * 1024)  # 51MB
        uploaded_file = SimpleUploadedFile(
            "test.txt",
            large_content,
            content_type="text/plain"
        )

        form_data = {
            'title': 'Test Article',
            'voice_id': '',
            'speed': '',
            'voice_preset': '',
        }

        form = ArticleSubmissionForm(
            data=form_data,
            files={'uploaded_file': uploaded_file},
            user=self.user
        )

        self.assertFalse(form.is_valid())
        self.assertIn('too large', str(form.errors))


class FileUploadViewTests(TestCase):
    """Test the article creation view with file uploads."""

    def setUp(self):
        """Set up test user and feed."""
        self.user = User.objects.create_user(
            username="testuser",
            email="test@example.com",
            password="testpass"
        )
        self.feed = Feed.objects.create(
            user=self.user,
            name="Test Feed"
        )
        self.client.login(username="testuser", password="testpass")

    @patch('text_to_audio.services.file_processing.FileProcessingService.process_uploaded_file')
    @patch('text_to_audio.tasks.process_article.delay')
    def test_article_creation_with_file_upload(self, mock_process_task, mock_file_processing):
        """Test article creation with file upload."""
        # Mock file processing
        mock_file_processing.return_value = (
            True,  # success
            "This is the extracted text content from the uploaded file.",  # extracted_text
            "txt",  # detected_file_type
            None   # error
        )

        # Mock Celery task
        mock_task = type('MockTask', (), {'id': 'test-task-id'})()
        mock_process_task.return_value = mock_task

        uploaded_file = SimpleUploadedFile(
            "test_article.txt",
            b"This is test content for article processing.",
            content_type="text/plain"
        )

        response = self.client.post(
            reverse('feed-article-create', kwargs={'feed_id': self.feed.id}),
            {
                'title': 'Uploaded Article',
                'uploaded_file': uploaded_file,
                'voice_id': '',
                'speed': '',
                'voice_preset': '',
            }
        )

        # Should redirect to feed articles page
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse('feed-articles', kwargs={'feed_id': self.feed.id}))

        # Check that article was created
        self.assertEqual(Article.objects.count(), 1)

        article = Article.objects.first()
        self.assertEqual(article.title, 'Uploaded Article')
        self.assertEqual(article.text_content, "This is the extracted text content from the uploaded file.")
        self.assertEqual(article.file_type, "txt")
        self.assertEqual(article.feed, self.feed)
        self.assertEqual(article.status, Article.PROCESSING)

        # Check that file processing was called
        mock_file_processing.assert_called_once()

        # Check that processing task was queued
        mock_process_task.assert_called_once_with(article.id)

    @patch('text_to_audio.services.file_processing.FileProcessingService.process_uploaded_file')
    def test_article_creation_with_file_processing_error(self, mock_file_processing):
        """Test article creation when file processing fails."""
        # Mock file processing failure
        mock_file_processing.return_value = (
            False,  # success
            "",     # extracted_text
            "txt",  # detected_file_type
            "Failed to extract text from the file"  # error
        )

        uploaded_file = SimpleUploadedFile(
            "test_article.txt",
            b"This is test content.",
            content_type="text/plain"
        )

        response = self.client.post(
            reverse('feed-article-create', kwargs={'feed_id': self.feed.id}),
            {
                'title': 'Uploaded Article',
                'uploaded_file': uploaded_file,
                'voice_id': '',
                'speed': '',
                'voice_preset': '',
            }
        )

        # Should return to form with error
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Failed to extract text from the file")

        # No article should be created
        self.assertEqual(Article.objects.count(), 0)

    @patch('text_to_audio.services.file_processing.FileProcessingService.process_uploaded_file')
    @patch('text_to_audio.tasks.process_article.delay')
    def test_article_creation_title_generation_from_file(self, mock_process_task, mock_file_processing):
        """Test automatic title generation from file content."""
        # Mock file processing
        mock_file_processing.return_value = (
            True,  # success
            "Article Title\n\nThis is the body content of the article.",  # extracted_text
            "txt",  # detected_file_type
            None   # error
        )

        # Mock Celery task
        mock_task = type('MockTask', (), {'id': 'test-task-id'})()
        mock_process_task.return_value = mock_task

        uploaded_file = SimpleUploadedFile(
            "document.txt",
            b"File content here.",
            content_type="text/plain"
        )

        response = self.client.post(
            reverse('feed-article-create', kwargs={'feed_id': self.feed.id}),
            {
                # No title provided
                'uploaded_file': uploaded_file,
                'voice_id': '',
                'speed': '',
                'voice_preset': '',
            }
        )

        # Should redirect successfully
        self.assertEqual(response.status_code, 302)

        # Check that article was created with auto-generated title
        article = Article.objects.first()
        self.assertEqual(article.title, 'Article Title')  # First line becomes title
        self.assertEqual(article.text_content, "Article Title\n\nThis is the body content of the article.")

    @patch('text_to_audio.services.file_processing.FileProcessingService.process_uploaded_file')
    @patch('text_to_audio.tasks.process_article.delay')
    def test_article_creation_title_from_filename(self, mock_process_task, mock_file_processing):
        """Test title generation from filename when content doesn't have a clear title."""
        # Mock file processing with content that doesn't have a clear title
        mock_file_processing.return_value = (
            True,  # success
            "This is a long paragraph that starts immediately without a clear title and continues for a while...",  # extracted_text
            "txt",  # detected_file_type
            None   # error
        )

        # Mock Celery task
        mock_task = type('MockTask', (), {'id': 'test-task-id'})()
        mock_process_task.return_value = mock_task

        uploaded_file = SimpleUploadedFile(
            "my_interesting_document.txt",
            b"File content here.",
            content_type="text/plain"
        )

        response = self.client.post(
            reverse('feed-article-create', kwargs={'feed_id': self.feed.id}),
            {
                # No title provided
                'uploaded_file': uploaded_file,
                'voice_id': '',
                'speed': '',
                'voice_preset': '',
            }
        )

        # Should redirect successfully
        self.assertEqual(response.status_code, 302)

        # Check that article was created with truncated content as title
        article = Article.objects.first()
        # Should use first 100 characters as title since first line is too long
        expected_title = "This is a long paragraph that starts immediately without a clear title and continues fo..."
        self.assertEqual(article.title, expected_title)


class FileUploadModelTests(TestCase):
    """Test the Article model with file upload fields."""

    def setUp(self):
        """Set up test user and feed."""
        self.user = User.objects.create_user(
            username="testuser",
            email="test@example.com",
            password="testpass"
        )
        self.feed = Feed.objects.create(
            user=self.user,
            name="Test Feed"
        )

    def test_article_with_file_fields(self):
        """Test creating an article with file upload fields."""
        article = Article.objects.create(
            feed=self.feed,
            title="Test Article",
            text_content="Extracted content from uploaded file",
            file_type="pdf",
            status=Article.PROCESSING
        )

        # Verify the fields are saved correctly
        self.assertEqual(article.file_type, "pdf")
        self.assertEqual(article.text_content, "Extracted content from uploaded file")

        # Test string representation
        self.assertEqual(str(article), "Test Article")

    def test_article_file_type_choices(self):
        """Test that file_type field accepts valid choices."""
        valid_types = ["pdf", "html", "txt"]

        for file_type in valid_types:
            article = Article.objects.create(
                feed=self.feed,
                title=f"Test Article {file_type}",
                text_content="Test content",
                file_type=file_type,
                status=Article.PROCESSING
            )
            self.assertEqual(article.file_type, file_type)

    def test_article_without_file_fields(self):
        """Test that articles can still be created without file fields (URL/text only)."""
        article = Article.objects.create(
            feed=self.feed,
            title="URL Article",
            source_url="https://example.com/article",
            status=Article.PROCESSING
        )

        # File fields should be None/empty
        self.assertIsNone(article.file_type)
        self.assertFalse(article.uploaded_file)
        self.assertEqual(article.source_url, "https://example.com/article")
