"""Tests for FeedEmailService — TDD tests written before implementation."""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from text_to_audio.models import Feed
from text_to_audio.services.feed_email_service import FeedEmailResult, FeedEmailService

User = get_user_model()


# AIDEV-NOTE: override Mailgun settings to prevent post_save signal from generating emails on Feed creation
@override_settings(MAILGUN_API_KEY="", MAILGUN_DOMAIN="")
class FeedEmailServiceTests(TestCase):
    """Tests for FeedEmailService.generate_email_for_feed()."""

    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="testpass")
        self.feed = Feed.objects.create(user=self.user, name="Test Feed")
        self.service = FeedEmailService()

    def test_generate_email_feed_already_has_email(self):
        """Returns early with info when feed already has an email."""
        self.feed.inbound_email = "existing@mg.example.com"
        self.feed.save(update_fields=["inbound_email"])

        result = self.service.generate_email_for_feed(self.feed)

        self.assertFalse(result.success)
        self.assertEqual(result.level, "info")
        self.assertIn("already has an email", result.message)
        self.assertEqual(result.email, "existing@mg.example.com")

    def test_generate_email_mailgun_not_configured(self):
        """Returns error when Mailgun is not configured (class-level override applies)."""
        result = self.service.generate_email_for_feed(self.feed)

        self.assertFalse(result.success)
        self.assertEqual(result.level, "error")
        self.assertIn("not configured", result.message.lower())

    @override_settings(MAILGUN_API_KEY="test-key", MAILGUN_DOMAIN="mg.example.com")
    @patch.object(Feed, "generate_inbound_email", return_value=None)
    def test_generate_email_generation_fails(self, mock_gen):
        """Returns error when email generation fails."""
        result = self.service.generate_email_for_feed(self.feed)

        self.assertFalse(result.success)
        self.assertEqual(result.level, "error")
        self.assertIn("failed to generate", result.message.lower())

    @override_settings(
        MAILGUN_API_KEY="test-key",
        MAILGUN_DOMAIN="mg.example.com",
        SITE_URL="https://example.com",
    )
    @patch("text_to_audio.services.feed_email_service.MailgunService")
    @patch.object(
        Feed, "generate_inbound_email", return_value="happy-river-42@mg.example.com"
    )
    def test_generate_email_success_with_route(self, mock_gen, mock_mailgun_cls):
        """Full success: email generated + Mailgun route created + feed saved."""
        mock_mailgun = mock_mailgun_cls.return_value
        mock_mailgun.create_route.return_value = (True, "route-123", None)

        result = self.service.generate_email_for_feed(self.feed)

        self.assertTrue(result.success)
        self.assertEqual(result.level, "success")
        self.assertEqual(result.email, "happy-river-42@mg.example.com")
        self.assertEqual(result.route_id, "route-123")

        # Verify feed was saved
        self.feed.refresh_from_db()
        self.assertEqual(self.feed.inbound_email, "happy-river-42@mg.example.com")
        self.assertEqual(self.feed.mailgun_route_id, "route-123")

    @override_settings(
        MAILGUN_API_KEY="test-key",
        MAILGUN_DOMAIN="mg.example.com",
        SITE_URL="https://example.com",
    )
    @patch("text_to_audio.services.feed_email_service.MailgunService")
    @patch.object(
        Feed, "generate_inbound_email", return_value="happy-river-42@mg.example.com"
    )
    def test_generate_email_success_route_fails(self, mock_gen, mock_mailgun_cls):
        """Email saved but route creation fails — partial success with warning."""
        mock_mailgun = mock_mailgun_cls.return_value
        mock_mailgun.create_route.return_value = (False, None, "API error")

        result = self.service.generate_email_for_feed(self.feed)

        self.assertTrue(result.success)
        self.assertEqual(result.level, "warning")
        self.assertEqual(result.email, "happy-river-42@mg.example.com")
        self.assertIsNone(result.route_id)
        self.assertIn("route", result.message.lower())

        # Email saved but no route ID
        self.feed.refresh_from_db()
        self.assertEqual(self.feed.inbound_email, "happy-river-42@mg.example.com")
        self.assertIsNone(self.feed.mailgun_route_id)

    @override_settings(
        MAILGUN_API_KEY="test-key",
        MAILGUN_DOMAIN="mg.example.com",
        SITE_URL=None,
    )
    @patch.object(
        Feed, "generate_inbound_email", return_value="happy-river-42@mg.example.com"
    )
    def test_generate_email_no_site_url(self, mock_gen):
        """Email saved without route when SITE_URL is not configured."""
        result = self.service.generate_email_for_feed(self.feed)

        self.assertTrue(result.success)
        self.assertEqual(result.level, "warning")
        self.assertEqual(result.email, "happy-river-42@mg.example.com")
        self.assertIsNone(result.route_id)
        self.assertIn("SITE_URL", result.message)

        self.feed.refresh_from_db()
        self.assertEqual(self.feed.inbound_email, "happy-river-42@mg.example.com")

    @override_settings(
        MAILGUN_API_KEY="test-key",
        MAILGUN_DOMAIN="mg.example.com",
        SITE_URL="https://example.com",
    )
    @patch("text_to_audio.services.feed_email_service.MailgunService")
    @patch.object(
        Feed, "generate_inbound_email", return_value="happy-river-42@mg.example.com"
    )
    def test_generate_email_saves_correct_fields(self, mock_gen, mock_mailgun_cls):
        """Verifies only inbound_email and mailgun_route_id are saved."""
        mock_mailgun = mock_mailgun_cls.return_value
        mock_mailgun.create_route.return_value = (True, "route-456", None)

        original_name = self.feed.name

        self.service.generate_email_for_feed(self.feed)

        self.feed.refresh_from_db()
        self.assertEqual(self.feed.inbound_email, "happy-river-42@mg.example.com")
        self.assertEqual(self.feed.mailgun_route_id, "route-456")
        self.assertEqual(self.feed.name, original_name)


class FeedEmailResultTests(TestCase):
    """Tests for the FeedEmailResult dataclass."""

    def test_default_values(self):
        result = FeedEmailResult(success=True)
        self.assertTrue(result.success)
        self.assertIsNone(result.email)
        self.assertIsNone(result.route_id)
        self.assertEqual(result.message, "")
        self.assertEqual(result.level, "info")

    def test_all_fields(self):
        result = FeedEmailResult(
            success=True,
            email="test@example.com",
            route_id="rt-123",
            message="Done",
            level="success",
        )
        self.assertTrue(result.success)
        self.assertEqual(result.email, "test@example.com")
        self.assertEqual(result.route_id, "rt-123")
        self.assertEqual(result.message, "Done")
        self.assertEqual(result.level, "success")
