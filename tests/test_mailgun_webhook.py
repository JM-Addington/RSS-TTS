"""Tests for Mailgun webhook handling and async email processing."""

import base64
import hashlib
import hmac
import time
from unittest.mock import MagicMock, patch

import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, RequestFactory, TestCase, override_settings
from django.urls import reverse

from text_to_audio.mailgun_views import mailgun_incoming_webhook
from text_to_audio.models import Article, Feed
from text_to_audio.tasks import process_incoming_email

User = get_user_model()


@override_settings(MAILGUN_API_KEY=None, MAILGUN_DOMAIN=None)
class MailgunWebhookTestCase(TestCase):
    """Tests for the Mailgun incoming webhook endpoint."""

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
            inbound_email="test-feed@mg.example.com",
        )
        # Test webhook signing key
        self.webhook_key = "test-webhook-key"

    def _generate_signature(self, timestamp, token):
        """Generate a valid Mailgun webhook signature."""
        message = f"{timestamp}{token}"
        signature = hmac.new(
            self.webhook_key.encode(),
            message.encode(),
            hashlib.sha256,
        ).hexdigest()
        return signature

    @patch("text_to_audio.mailgun_views.MailgunService")
    @patch("text_to_audio.mailgun_views.process_incoming_email.delay")
    def test_webhook_accepts_email_and_queues_task(
        self, mock_delay, mock_mailgun_service
    ):
        """Test that webhook accepts email quickly and queues async task."""
        # Mock signature verification
        mock_instance = MagicMock()
        mock_instance.verify_webhook_signature.return_value = True
        mock_mailgun_service.return_value = mock_instance

        timestamp = str(int(time.time()))
        token = "test-token"
        signature = self._generate_signature(timestamp, token)

        response = self.client.post(
            reverse("mailgun-incoming-webhook"),
            {
                "timestamp": timestamp,
                "token": token,
                "signature": signature,
                "recipient": "test-feed@mg.example.com",
                "sender": "sender@example.com",
                "subject": "Test Email Subject",
                "body-plain": "This is the email content.",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"accepted", response.content.lower())

        # Verify task was queued
        mock_delay.assert_called_once()
        call_args = mock_delay.call_args[0][0]
        self.assertEqual(call_args["feed_id"], self.feed.id)
        self.assertEqual(call_args["subject"], "Test Email Subject")
        self.assertEqual(call_args["text_content"], "This is the email content.")

    @patch("text_to_audio.mailgun_views.MailgunService")
    def test_webhook_rejects_invalid_signature(self, mock_mailgun_service):
        """Test that webhook rejects requests with invalid signature."""
        mock_instance = MagicMock()
        mock_instance.verify_webhook_signature.return_value = False
        mock_mailgun_service.return_value = mock_instance

        response = self.client.post(
            reverse("mailgun-incoming-webhook"),
            {
                "timestamp": "12345",
                "token": "bad-token",
                "signature": "invalid-signature",
                "recipient": "test-feed@mg.example.com",
                "body-plain": "Content",
            },
        )

        self.assertEqual(response.status_code, 403)

    @patch("text_to_audio.mailgun_views.MailgunService")
    def test_webhook_rejects_unknown_recipient(self, mock_mailgun_service):
        """Test that webhook rejects emails to unknown recipients."""
        mock_instance = MagicMock()
        mock_instance.verify_webhook_signature.return_value = True
        mock_mailgun_service.return_value = mock_instance

        response = self.client.post(
            reverse("mailgun-incoming-webhook"),
            {
                "timestamp": "12345",
                "token": "token",
                "signature": "sig",
                "recipient": "unknown@mg.example.com",
                "body-plain": "Content",
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn(b"No feed found", response.content)

    @patch("text_to_audio.mailgun_views.MailgunService")
    @patch("text_to_audio.mailgun_views.process_incoming_email.delay")
    def test_webhook_handles_attachments(self, mock_delay, mock_mailgun_service):
        """Test that webhook properly encodes attachments for async processing."""
        mock_instance = MagicMock()
        mock_instance.verify_webhook_signature.return_value = True
        mock_mailgun_service.return_value = mock_instance

        # Create a test PDF attachment
        pdf_content = b"%PDF-1.4 test content"
        pdf_file = SimpleUploadedFile(
            "test.pdf",
            pdf_content,
            content_type="application/pdf",
        )

        response = self.client.post(
            reverse("mailgun-incoming-webhook"),
            {
                "timestamp": "12345",
                "token": "token",
                "signature": "sig",
                "recipient": "test-feed@mg.example.com",
                "sender": "sender@example.com",
                "subject": "Email with PDF",
                "body-plain": "See attached.",
                "attachment-count": "1",
                "attachment-1": pdf_file,
            },
        )

        self.assertEqual(response.status_code, 200)

        # Verify attachment was base64 encoded in task payload
        call_args = mock_delay.call_args[0][0]
        self.assertEqual(len(call_args["attachments"]), 1)
        attachment = call_args["attachments"][0]
        self.assertEqual(attachment["filename"], "test.pdf")
        self.assertEqual(attachment["content_type"], "application/pdf")

        # Verify base64 data decodes correctly
        decoded_data = base64.b64decode(attachment["data"])
        self.assertEqual(decoded_data, pdf_content)


    @patch("text_to_audio.mailgun_views.MailgunService")
    @patch("text_to_audio.mailgun_views.process_incoming_email.delay")
    def test_webhook_rejects_oversized_attachment(
        self, mock_delay, mock_mailgun_service
    ):
        """Test that webhook skips attachments exceeding 10MB."""
        mock_instance = MagicMock()
        mock_instance.verify_webhook_signature.return_value = True
        mock_mailgun_service.return_value = mock_instance

        # Create an oversized attachment (10MB + 1 byte)
        oversized_content = b"x" * (10 * 1024 * 1024 + 1)
        oversized_file = SimpleUploadedFile(
            "huge.pdf",
            oversized_content,
            content_type="application/pdf",
        )

        response = self.client.post(
            reverse("mailgun-incoming-webhook"),
            {
                "timestamp": "12345",
                "token": "token",
                "signature": "sig",
                "recipient": "test-feed@mg.example.com",
                "sender": "sender@example.com",
                "subject": "Email with huge PDF",
                "body-plain": "See attached.",
                "attachment-count": "1",
                "attachment-1": oversized_file,
            },
        )

        # Webhook should still return 200 (valid request, just skip the file)
        self.assertEqual(response.status_code, 200)

        # Verify the oversized attachment was NOT included in the task payload
        call_args = mock_delay.call_args[0][0]
        self.assertEqual(len(call_args["attachments"]), 0)

    @patch("text_to_audio.mailgun_views.MailgunService")
    @patch("text_to_audio.mailgun_views.process_incoming_email.delay")
    def test_webhook_accepts_attachment_at_size_limit(
        self, mock_delay, mock_mailgun_service
    ):
        """Test that webhook accepts attachments exactly at the 10MB limit."""
        mock_instance = MagicMock()
        mock_instance.verify_webhook_signature.return_value = True
        mock_mailgun_service.return_value = mock_instance

        # Create an attachment exactly at the limit (10MB)
        limit_content = b"x" * (10 * 1024 * 1024)
        limit_file = SimpleUploadedFile(
            "exact.pdf",
            limit_content,
            content_type="application/pdf",
        )

        response = self.client.post(
            reverse("mailgun-incoming-webhook"),
            {
                "timestamp": "12345",
                "token": "token",
                "signature": "sig",
                "recipient": "test-feed@mg.example.com",
                "sender": "sender@example.com",
                "subject": "Email with exact limit PDF",
                "body-plain": "See attached.",
                "attachment-count": "1",
                "attachment-1": limit_file,
            },
        )

        self.assertEqual(response.status_code, 200)

        # Verify attachment was accepted
        call_args = mock_delay.call_args[0][0]
        self.assertEqual(len(call_args["attachments"]), 1)
        self.assertEqual(call_args["attachments"][0]["filename"], "exact.pdf")

    @patch("text_to_audio.mailgun_views.MailgunService")
    @patch("text_to_audio.mailgun_views.process_incoming_email.delay")
    def test_webhook_skips_oversized_but_keeps_valid_attachments(
        self, mock_delay, mock_mailgun_service
    ):
        """Test that only oversized attachments are skipped; valid ones are kept."""
        mock_instance = MagicMock()
        mock_instance.verify_webhook_signature.return_value = True
        mock_mailgun_service.return_value = mock_instance

        # One valid small attachment
        small_content = b"small file content"
        small_file = SimpleUploadedFile(
            "small.txt",
            small_content,
            content_type="text/plain",
        )
        # One oversized attachment
        oversized_content = b"x" * (10 * 1024 * 1024 + 1)
        oversized_file = SimpleUploadedFile(
            "huge.pdf",
            oversized_content,
            content_type="application/pdf",
        )

        response = self.client.post(
            reverse("mailgun-incoming-webhook"),
            {
                "timestamp": "12345",
                "token": "token",
                "signature": "sig",
                "recipient": "test-feed@mg.example.com",
                "sender": "sender@example.com",
                "subject": "Mixed attachments",
                "body-plain": "See attached.",
                "attachment-count": "2",
                "attachment-1": small_file,
                "attachment-2": oversized_file,
            },
        )

        self.assertEqual(response.status_code, 200)

        # Only the small attachment should be included
        call_args = mock_delay.call_args[0][0]
        self.assertEqual(len(call_args["attachments"]), 1)
        self.assertEqual(call_args["attachments"][0]["filename"], "small.txt")

    @patch("text_to_audio.mailgun_views.MailgunService")
    @patch("text_to_audio.mailgun_views.process_incoming_email.delay")
    def test_webhook_logs_oversized_attachment(
        self, mock_delay, mock_mailgun_service
    ):
        """Test that skipping an oversized attachment logs a warning."""
        mock_instance = MagicMock()
        mock_instance.verify_webhook_signature.return_value = True
        mock_mailgun_service.return_value = mock_instance

        oversized_content = b"x" * (10 * 1024 * 1024 + 1)
        oversized_file = SimpleUploadedFile(
            "huge.pdf",
            oversized_content,
            content_type="application/pdf",
        )

        with self.assertLogs("text_to_audio.mailgun_views", level="WARNING") as cm:
            self.client.post(
                reverse("mailgun-incoming-webhook"),
                {
                    "timestamp": "12345",
                    "token": "token",
                    "signature": "sig",
                    "recipient": "test-feed@mg.example.com",
                    "sender": "sender@example.com",
                    "subject": "Oversized",
                    "body-plain": "Content.",
                    "attachment-count": "1",
                    "attachment-1": oversized_file,
                },
            )

        # Verify the warning log contains filename and size info
        log_output = "\n".join(cm.output)
        self.assertIn("huge.pdf", log_output)
        self.assertIn("oversized", log_output.lower())

    @patch("text_to_audio.mailgun_views.MailgunService")
    @patch("text_to_audio.mailgun_views.process_incoming_email.delay")
    def test_webhook_rejects_invalid_content_type_attachment(
        self, mock_delay, mock_mailgun_service
    ):
        """Test that webhook skips attachments with disallowed content types."""
        mock_instance = MagicMock()
        mock_instance.verify_webhook_signature.return_value = True
        mock_mailgun_service.return_value = mock_instance

        binary_file = SimpleUploadedFile(
            "data.bin",
            b"binary content",
            content_type="application/octet-stream",
        )

        response = self.client.post(
            reverse("mailgun-incoming-webhook"),
            {
                "timestamp": "12345",
                "token": "token",
                "signature": "sig",
                "recipient": "test-feed@mg.example.com",
                "sender": "sender@example.com",
                "subject": "Bad attachment type",
                "body-plain": "See attached.",
                "attachment-count": "1",
                "attachment-1": binary_file,
            },
        )

        self.assertEqual(response.status_code, 200)

        # Verify the invalid attachment was NOT included in the task payload
        call_args = mock_delay.call_args[0][0]
        self.assertEqual(len(call_args["attachments"]), 0)

    @patch("text_to_audio.mailgun_views.MailgunService")
    @patch("text_to_audio.mailgun_views.process_incoming_email.delay")
    def test_webhook_accepts_valid_content_types(
        self, mock_delay, mock_mailgun_service
    ):
        """Test that webhook accepts all allowed content types."""
        mock_instance = MagicMock()
        mock_instance.verify_webhook_signature.return_value = True
        mock_mailgun_service.return_value = mock_instance

        valid_types = [
            ("test.pdf", "application/pdf"),
            ("test.html", "text/html"),
            ("test.txt", "text/plain"),
            ("test.md", "text/markdown"),
            ("test2.md", "text/x-markdown"),
        ]

        for filename, content_type in valid_types:
            with self.subTest(content_type=content_type):
                test_file = SimpleUploadedFile(
                    filename,
                    b"test content",
                    content_type=content_type,
                )

                response = self.client.post(
                    reverse("mailgun-incoming-webhook"),
                    {
                        "timestamp": "12345",
                        "token": "token",
                        "signature": "sig",
                        "recipient": "test-feed@mg.example.com",
                        "sender": "sender@example.com",
                        "subject": "Valid attachment",
                        "body-plain": "See attached.",
                        "attachment-count": "1",
                        "attachment-1": test_file,
                    },
                )

                self.assertEqual(response.status_code, 200)
                call_args = mock_delay.call_args[0][0]
                self.assertEqual(
                    len(call_args["attachments"]),
                    1,
                    f"Expected attachment with content_type={content_type} to be accepted",
                )
                self.assertEqual(
                    call_args["attachments"][0]["content_type"], content_type
                )

    @patch("text_to_audio.mailgun_views.MailgunService")
    @patch("text_to_audio.mailgun_views.process_incoming_email.delay")
    def test_webhook_skips_invalid_but_keeps_valid_attachments(
        self, mock_delay, mock_mailgun_service
    ):
        """Test that only invalid content-type attachments are skipped; valid ones kept."""
        mock_instance = MagicMock()
        mock_instance.verify_webhook_signature.return_value = True
        mock_mailgun_service.return_value = mock_instance

        valid_file = SimpleUploadedFile(
            "doc.pdf",
            b"pdf content",
            content_type="application/pdf",
        )
        invalid_file = SimpleUploadedFile(
            "image.png",
            b"png content",
            content_type="image/png",
        )

        response = self.client.post(
            reverse("mailgun-incoming-webhook"),
            {
                "timestamp": "12345",
                "token": "token",
                "signature": "sig",
                "recipient": "test-feed@mg.example.com",
                "sender": "sender@example.com",
                "subject": "Mixed content types",
                "body-plain": "See attached.",
                "attachment-count": "2",
                "attachment-1": valid_file,
                "attachment-2": invalid_file,
            },
        )

        self.assertEqual(response.status_code, 200)

        # Only the valid attachment should be included
        call_args = mock_delay.call_args[0][0]
        self.assertEqual(len(call_args["attachments"]), 1)
        self.assertEqual(call_args["attachments"][0]["filename"], "doc.pdf")

    @patch("text_to_audio.mailgun_views.process_incoming_email.delay")
    @patch("text_to_audio.mailgun_views.MailgunService")
    def test_content_type_mime_param_stripping_accepts_valid(
        self, mock_mailgun_service, mock_delay
    ):
        """Test that content-type MIME params (e.g. charset=utf-8) are stripped before validation.

        AIDEV-NOTE: Mailgun sends content-type with params like 'text/plain; charset=utf-8'.
        Django's test client strips these during multipart parsing, so we inject a mock file
        into request.FILES to simulate real Mailgun behavior.
        """
        mock_instance = MagicMock()
        mock_instance.verify_webhook_signature.return_value = True
        mock_mailgun_service.return_value = mock_instance

        mock_file = MagicMock()
        mock_file.name = "notes.txt"
        mock_file.size = 100
        mock_file.content_type = "text/plain; charset=utf-8"
        mock_file.read.return_value = b"some text content"

        factory = RequestFactory()
        request = factory.post(
            reverse("mailgun-incoming-webhook"),
            {
                "timestamp": "12345",
                "token": "token",
                "signature": "sig",
                "recipient": "test-feed@mg.example.com",
                "sender": "sender@example.com",
                "subject": "Text with charset",
                "body-plain": "See attached.",
                "attachment-count": "1",
            },
        )
        request.FILES["attachment-1"] = mock_file

        response = mailgun_incoming_webhook(request)

        self.assertEqual(response.status_code, 200)
        mock_delay.assert_called_once()
        call_args = mock_delay.call_args[0][0]
        self.assertEqual(len(call_args["attachments"]), 1)
        self.assertEqual(call_args["attachments"][0]["filename"], "notes.txt")

    @patch("text_to_audio.mailgun_views.process_incoming_email.delay")
    @patch("text_to_audio.mailgun_views.MailgunService")
    def test_content_type_mime_param_stripping_rejects_invalid(
        self, mock_mailgun_service, mock_delay
    ):
        """Test that invalid content types with MIME params are still rejected."""
        mock_instance = MagicMock()
        mock_instance.verify_webhook_signature.return_value = True
        mock_mailgun_service.return_value = mock_instance

        mock_file = MagicMock()
        mock_file.name = "data.bin"
        mock_file.size = 100
        mock_file.content_type = "application/octet-stream; charset=utf-8"
        mock_file.read.return_value = b"binary content"

        factory = RequestFactory()
        request = factory.post(
            reverse("mailgun-incoming-webhook"),
            {
                "timestamp": "12345",
                "token": "token",
                "signature": "sig",
                "recipient": "test-feed@mg.example.com",
                "sender": "sender@example.com",
                "subject": "Bad type with params",
                "body-plain": "See attached.",
                "attachment-count": "1",
            },
        )
        request.FILES["attachment-1"] = mock_file

        response = mailgun_incoming_webhook(request)

        self.assertEqual(response.status_code, 200)
        mock_delay.assert_called_once()
        call_args = mock_delay.call_args[0][0]
        self.assertEqual(len(call_args["attachments"]), 0)

    @patch("text_to_audio.mailgun_views.MailgunService")
    @patch("text_to_audio.mailgun_views.process_incoming_email.delay")
    def test_webhook_logs_invalid_content_type(
        self, mock_delay, mock_mailgun_service
    ):
        """Test that skipping an invalid content-type attachment logs a warning."""
        mock_instance = MagicMock()
        mock_instance.verify_webhook_signature.return_value = True
        mock_mailgun_service.return_value = mock_instance

        invalid_file = SimpleUploadedFile(
            "image.jpg",
            b"jpeg content",
            content_type="image/jpeg",
        )

        with self.assertLogs("text_to_audio.mailgun_views", level="WARNING") as cm:
            self.client.post(
                reverse("mailgun-incoming-webhook"),
                {
                    "timestamp": "12345",
                    "token": "token",
                    "signature": "sig",
                    "recipient": "test-feed@mg.example.com",
                    "sender": "sender@example.com",
                    "subject": "Bad type",
                    "body-plain": "Content.",
                    "attachment-count": "1",
                    "attachment-1": invalid_file,
                },
            )

        log_output = "\n".join(cm.output)
        self.assertIn("image.jpg", log_output)
        self.assertIn("image/jpeg", log_output)


class ProcessIncomingEmailTaskTestCase(TestCase):
    """Tests for the process_incoming_email Celery task."""

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
    def test_task_creates_article_from_plain_text(self, mock_process_article):
        """Test that task creates article from plain text email."""
        mock_process_article.return_value = MagicMock(id="task-123")

        payload = {
            "feed_id": self.feed.id,
            "subject": "Test Subject",
            "text_content": "This is the email body content.",
            "sender": "sender@example.com",
            "attachments": [],
        }

        result = process_incoming_email(payload)

        self.assertIn("created successfully", result)

        # Verify article was created
        article = Article.objects.get(feed=self.feed)
        self.assertEqual(article.title, "Test Subject")
        self.assertEqual(article.text_content, "This is the email body content.")
        self.assertEqual(article.status, Article.PROCESSING)

        # Verify TTS processing was queued
        mock_process_article.assert_called_once_with(article.pk)

    @patch("text_to_audio.tasks.process_article.delay")
    @patch("text_to_audio.utils.extract_text_from_pdf")
    @override_settings(ENABLE_EMAIL_CONTENT_CLEANING=False)
    def test_task_extracts_pdf_attachment(self, mock_extract_pdf, mock_process_article):
        """Test that task extracts text from PDF attachments."""
        mock_extract_pdf.return_value = "Extracted PDF content here."
        mock_process_article.return_value = MagicMock(id="task-123")

        # Create base64 encoded PDF data
        pdf_content = b"%PDF-1.4 test content"
        pdf_b64 = base64.b64encode(pdf_content).decode("ascii")

        payload = {
            "feed_id": self.feed.id,
            "subject": "Email Article",
            "text_content": "Fallback body text.",
            "sender": "sender@example.com",
            "attachments": [
                {
                    "filename": "document.pdf",
                    "content_type": "application/pdf",
                    "data": pdf_b64,
                }
            ],
        }

        result = process_incoming_email(payload)

        self.assertIn("created successfully", result)

        # Verify article used PDF content, not email body
        article = Article.objects.get(feed=self.feed)
        self.assertEqual(article.text_content, "Extracted PDF content here.")
        # Title should be derived from PDF filename
        self.assertEqual(article.title, "document")

    @patch("text_to_audio.tasks.process_article.delay")
    @patch("text_to_audio.services.email_cleaning_service.EmailCleaningService")
    @override_settings(ENABLE_EMAIL_CONTENT_CLEANING=True)
    def test_task_cleans_email_content(
        self, mock_cleaning_service, mock_process_article
    ):
        """Test that task applies LLM cleaning to email body."""
        # Mock the cleaning service
        mock_service_instance = MagicMock()
        mock_service_instance.clean_email_content.return_value = (
            True,
            "Cleaned content without ads.",
            {
                "content_type": "newsletter",
                "confidence": "high",
                "reduction_percent": 40,
            },
            None,
        )
        mock_cleaning_service.return_value = mock_service_instance
        mock_process_article.return_value = MagicMock(id="task-123")

        payload = {
            "feed_id": self.feed.id,
            "subject": "Newsletter",
            "text_content": "Original content with lots of ads and boilerplate.",
            "sender": "sender@example.com",
            "attachments": [],
        }

        result = process_incoming_email(payload)

        self.assertIn("created successfully", result)

        # Verify cleaning service was called
        mock_service_instance.clean_email_content.assert_called_once_with(
            "Original content with lots of ads and boilerplate.", "Newsletter"
        )

        # Verify article used cleaned content
        article = Article.objects.get(feed=self.feed)
        self.assertEqual(article.text_content, "Cleaned content without ads.")

    def test_task_handles_missing_feed(self):
        """Test that task handles missing feed gracefully."""
        payload = {
            "feed_id": 99999,  # Non-existent feed
            "subject": "Test",
            "text_content": "Content",
            "sender": "sender@example.com",
            "attachments": [],
        }

        result = process_incoming_email(payload)

        self.assertIn("not found", result)

        # Verify no article was created
        self.assertEqual(Article.objects.count(), 0)

    @patch("text_to_audio.tasks.process_article.delay")
    @override_settings(ENABLE_EMAIL_CONTENT_CLEANING=False)
    def test_task_handles_empty_content(self, mock_process_article):
        """Test that task handles empty content gracefully."""
        payload = {
            "feed_id": self.feed.id,
            "subject": "Empty Email",
            "text_content": "",
            "sender": "sender@example.com",
            "attachments": [],
        }

        result = process_incoming_email(payload)

        self.assertIn("No text content", result)

        # Verify no article was created
        self.assertEqual(Article.objects.count(), 0)


@override_settings(MAILGUN_API_KEY=None, MAILGUN_DOMAIN=None)
class MailgunWebhookBrokerFailureTests(TestCase):
    """Tests for graceful handling when Celery broker is unavailable during webhook processing.

    AIDEV-NOTE: Returns 503 so Mailgun retries when broker comes back online.
    """

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username="webhookbrokeruser",
            email="webhookbroker@example.com",
            password="testpass123",
        )
        self.feed = Feed.objects.create(
            user=self.user,
            name="Webhook Broker Feed",
            inbound_email="broker-test@mg.example.com",
        )
        self.webhook_key = "test-webhook-key"

    @patch("text_to_audio.mailgun_views.MailgunService")
    @patch("text_to_audio.mailgun_views.process_incoming_email.delay")
    def test_broker_down_returns_503(self, mock_delay, mock_mailgun_service):
        """Webhook returns 503 when Celery broker is unavailable."""
        from kombu.exceptions import OperationalError

        mock_instance = MagicMock()
        mock_instance.verify_webhook_signature.return_value = True
        mock_mailgun_service.return_value = mock_instance
        mock_delay.side_effect = OperationalError("Connection refused")

        response = self.client.post(
            reverse("mailgun-incoming-webhook"),
            {
                "timestamp": str(int(time.time())),
                "token": "test-token",
                "signature": "test-sig",
                "recipient": "broker-test@mg.example.com",
                "sender": "sender@example.com",
                "subject": "Test Email",
                "body-plain": "Email content.",
            },
        )

        self.assertEqual(response.status_code, 503)

    @patch("text_to_audio.mailgun_views.MailgunService")
    @patch("text_to_audio.mailgun_views.process_incoming_email.delay")
    def test_redis_down_returns_503(self, mock_delay, mock_mailgun_service):
        """Webhook returns 503 when Redis is unavailable."""
        from redis.exceptions import ConnectionError as RedisConnectionError

        mock_instance = MagicMock()
        mock_instance.verify_webhook_signature.return_value = True
        mock_mailgun_service.return_value = mock_instance
        mock_delay.side_effect = RedisConnectionError("Connection refused")

        response = self.client.post(
            reverse("mailgun-incoming-webhook"),
            {
                "timestamp": str(int(time.time())),
                "token": "test-token",
                "signature": "test-sig",
                "recipient": "broker-test@mg.example.com",
                "sender": "sender@example.com",
                "subject": "Test Email",
                "body-plain": "Email content.",
            },
        )

        self.assertEqual(response.status_code, 503)


# For pytest compatibility
if __name__ == "__main__":
    pytest.main([__file__])
