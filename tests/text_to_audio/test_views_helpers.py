# flake8: noqa
# mypy: ignore-errors
"""Tests for ArticleMediaView helper methods."""

import os
import uuid

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase

from text_to_audio.models import Article, Feed
from text_to_audio.views import ArticleMediaView

User = get_user_model()


class ArticleMediaViewHelperTests(TestCase):
    """Tests for helper methods in ArticleMediaView."""

    def setUp(self):
        """Create user, feed and article for tests."""
        self.user = User.objects.create_user(  # type: ignore[attr-defined]
            username="helperuser", password="testpass"
        )
        self.feed = Feed.objects.create(user=self.user, name="Feed")
        self.article = Article.objects.create(
            feed=self.feed,
            title="A",
            status=Article.COMPLETED,
            audio_uuid=uuid.uuid4(),
        )
        self.view = ArticleMediaView()

    def _create_audio_file(self, path: str):
        """Helper to create a dummy file."""
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.write("dummy")

    def test_find_audio_file_uses_canonical_path(self):
        """_find_audio_file uses canonical path when available."""
        canonical_path = os.path.join(
            settings.MEDIA_ROOT, "articles", f"{self.article.audio_uuid}.mp3"
        )
        self._create_audio_file(canonical_path)

        result = self.view._find_audio_file(self.article)
        self.assertEqual(result, canonical_path)

    def test_find_audio_file_returns_none_when_missing(self):
        """_find_audio_file returns None when canonical file doesn't exist."""
        # Don't create the file
        result = self.view._find_audio_file(self.article)
        self.assertIsNone(result)

    def test_find_audio_file_handles_missing_audio_uuid(self):
        """_find_audio_file handles articles without audio_uuid."""
        article_no_uuid = Article.objects.create(
            feed=self.feed,
            title="No UUID",
            status=Article.COMPLETED,
            audio_uuid=None,
        )

        result = self.view._find_audio_file(article_no_uuid)
        self.assertIsNone(result)
