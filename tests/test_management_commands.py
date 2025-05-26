# flake8: noqa
# mypy: ignore-errors
"""Tests for the update_audio_uuids management command."""

import os
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase

from text_to_audio.models import Article, Feed

User = get_user_model()


class UpdateAudioUUIDsCommandTest(TestCase):
    """Tests for update_audio_uuids management command."""

    def setUp(self):
        """Create user and feed for testing."""
        self.user = User.objects.create_user(  # type: ignore[attr-defined]
            username="cmduser", password="pass"
        )
        self.feed = Feed.objects.create(user=self.user, name="Feed")

    def _create_old_file(self, article):
        """Create an audio file using old naming scheme."""
        path = Path(settings.BASE_DIR) / article.audio_file_path
        os.makedirs(path.parent, exist_ok=True)
        with open(path, "w") as f:
            f.write("data")
        return path

    def test_command_updates_missing_uuid(self):
        """Command assigns new UUID and renames file."""
        article = Article.objects.create(
            feed=self.feed,
            title="A",
            status=Article.COMPLETED,
            audio_uuid=None,
            audio_file_path=f"articles/{self.user.id}/{self.feed.id}/article_1.mp3",  # type: ignore[attr-defined]
        )
        self._create_old_file(article)

        call_command("update_audio_uuids")

        article.refresh_from_db()
        self.assertIsNotNone(article.audio_uuid)
        self.assertIn(str(article.audio_uuid), article.audio_file_path)
        new_path = Path(settings.BASE_DIR) / article.audio_file_path
        self.assertTrue(new_path.exists())
