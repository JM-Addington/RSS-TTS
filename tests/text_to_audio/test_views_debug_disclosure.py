# flake8: noqa
# mypy: ignore-errors
"""Tests for debug info disclosure fix in ArticleMediaView (#210)."""

import uuid
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from text_to_audio.models import Article, Feed

User = get_user_model()


class ArticleMediaViewDebugDisclosureTests(TestCase):
    """Verify that ArticleMediaView does not leak server paths in 404 responses."""

    def setUp(self):
        self.user = User.objects.create_user(  # type: ignore[attr-defined]
            username="debuguser", password="testpass"
        )
        self.feed = Feed.objects.create(user=self.user, name="Feed")
        self.article = Article.objects.create(
            feed=self.feed,
            title="Test Article",
            status=Article.COMPLETED,
            audio_uuid=uuid.uuid4(),
            audio_file_path="/fake/path/to/audio.mp3",
        )
        self.url = f"/audio/{self.article.audio_uuid}/"

    @override_settings(DEBUG=True)
    def test_debug_mode_does_not_leak_paths_in_response(self):
        """With DEBUG=True and missing audio file, 404 must not contain sensitive paths."""
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 404)
        content = response.content.decode()
        self.assertNotIn(str(settings.MEDIA_ROOT), content)
        self.assertNotIn(str(settings.BASE_DIR), content)
        self.assertNotIn(self.article.audio_file_path, content)
        self.assertEqual(content, "Audio file not found")

    @override_settings(DEBUG=True)
    @patch("text_to_audio.views.logger")
    def test_debug_mode_logs_diagnostic_info(self, mock_logger):
        """With DEBUG=True and missing audio file, diagnostic details are logged."""
        self.client.get(self.url)
        mock_logger.warning.assert_called_once()
        log_msg = mock_logger.warning.call_args[0][0]
        self.assertIn("Audio file not found", log_msg)
        # Verify the log call includes the article UUID as an arg
        log_args = mock_logger.warning.call_args[0]
        self.assertIn(self.article.audio_uuid, log_args)

    @override_settings(DEBUG=False)
    def test_non_debug_mode_generic_404(self):
        """With DEBUG=False and missing audio file, generic message is returned."""
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.content.decode(), "Audio file not found")
