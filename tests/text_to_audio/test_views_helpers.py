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

    def test_find_by_pattern_updates_article(self):
        """File found by pattern updates article path."""
        file_path = os.path.join(
            settings.MEDIA_ROOT, "articles", f"{self.article.audio_uuid}.mp3"
        )
        self._create_audio_file(file_path)

        result = self.view._find_by_pattern(self.article)
        self.assertEqual(result, file_path)
        self.article.refresh_from_db()
        rel = os.path.relpath(file_path, settings.MEDIA_ROOT)
        self.assertEqual(self.article.audio_file_path, rel)

    def test_resolve_path_relative(self):
        """Relative paths resolve to existing file."""
        file_path = os.path.join(
            settings.MEDIA_ROOT, "articles", f"{self.article.audio_uuid}.mp3"
        )
        self._create_audio_file(file_path)
        self.article.audio_file_path = os.path.relpath(file_path, settings.MEDIA_ROOT)
        self.article.save()

        result = self.view._resolve_path(self.article)
        self.assertEqual(result, file_path)

    def test_find_audio_file_fallback(self):
        """Fallback to pattern search when set path missing."""
        # Create file only at pattern location
        file_path = os.path.join(
            settings.MEDIA_ROOT, "articles", f"{self.article.audio_uuid}.mp3"
        )
        self._create_audio_file(file_path)
        self.article.audio_file_path = "nonexistent/path.mp3"
        self.article.save()

        result = self.view._find_audio_file(self.article)
        self.assertEqual(result, file_path)
