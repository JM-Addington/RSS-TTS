"""View-level tests for GenerateFeedEmailView after refactoring to use FeedEmailService."""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from text_to_audio.models import Feed
from text_to_audio.services.feed_email_service import FeedEmailResult

User = get_user_model()


# AIDEV-NOTE: override Mailgun settings to prevent post_save signal from generating emails
@override_settings(MAILGUN_API_KEY="", MAILGUN_DOMAIN="")
class GenerateFeedEmailViewTests(TestCase):
    """Tests for the refactored GenerateFeedEmailView (thin view delegating to service)."""

    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="testpass")
        self.user.profile.is_approved = True
        self.user.profile.save()

        self.other_user = User.objects.create_user(username="other", password="testpass")
        self.other_user.profile.is_approved = True
        self.other_user.profile.save()

        self.feed = Feed.objects.create(user=self.user, name="Test Feed")
        self.url = f"/feeds/{self.feed.pk}/generate-email/"

    def test_view_requires_login(self):
        """Unauthenticated requests are redirected to login."""
        response = self.client.post(self.url)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login", response.url)

    @patch("text_to_audio.services.feed_email_service.FeedEmailService.generate_email_for_feed")
    def test_view_calls_service_and_sets_messages(self, mock_generate):
        """View delegates to service and maps result to Django messages."""
        mock_generate.return_value = FeedEmailResult(
            success=True,
            email="test@mg.example.com",
            message="Successfully created email address: test@mg.example.com",
            level="success",
        )

        self.client.login(username="testuser", password="testpass")
        response = self.client.post(self.url, follow=True)

        mock_generate.assert_called_once()
        # Verify the feed argument
        call_feed = mock_generate.call_args[0][0]
        self.assertEqual(call_feed.pk, self.feed.pk)

        # Check Django messages
        msg_list = list(response.context["messages"])
        self.assertEqual(len(msg_list), 1)
        self.assertEqual(str(msg_list[0]), "Successfully created email address: test@mg.example.com")

    @patch("text_to_audio.services.feed_email_service.FeedEmailService.generate_email_for_feed")
    def test_view_redirects_to_feed_list_by_default(self, mock_generate):
        """Default redirect goes to feed-list."""
        mock_generate.return_value = FeedEmailResult(
            success=True, message="OK", level="info"
        )

        self.client.login(username="testuser", password="testpass")
        response = self.client.post(self.url)

        self.assertEqual(response.status_code, 302)
        self.assertIn("/feeds", response.url)

    @patch("text_to_audio.services.feed_email_service.FeedEmailService.generate_email_for_feed")
    def test_view_redirects_to_feed_articles_when_requested(self, mock_generate):
        """Redirect to feed-articles when POST param redirect=feed-articles."""
        mock_generate.return_value = FeedEmailResult(
            success=True, message="OK", level="info"
        )

        self.client.login(username="testuser", password="testpass")
        response = self.client.post(self.url, data={"redirect": "feed-articles"})

        self.assertEqual(response.status_code, 302)
        # feed-articles URL is /feeds/<feed_id>/
        self.assertEqual(response.url, f"/feeds/{self.feed.pk}/")

    def test_view_404_for_other_users_feed(self):
        """Returns 404 when trying to generate email for another user's feed."""
        self.client.login(username="other", password="testpass")
        response = self.client.post(self.url)
        self.assertEqual(response.status_code, 404)
