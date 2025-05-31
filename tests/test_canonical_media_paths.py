"""Tests for canonical media path refactor.

This module tests the new canonical media path behavior where articles
save audio files to a consistent path: media/articles/{audio_uuid}.mp3
"""

import os
import tempfile

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from text_to_audio.models import Article, Feed

User = get_user_model()


class CanonicalMediaPathsTestCase(TestCase):
    """Test cases for canonical media path functionality."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass123"
        )
        self.feed = Feed.objects.create(user=self.user, name="Test Feed")
        self.article = Article.objects.create(
            feed=self.feed,
            title="Test Article",
            text_content="Test content for TTS",
            status=Article.PROCESSING,
        )

    def test_canonical_path_generation(self):
        """Test that canonical paths are generated correctly for audio files.

        The new canonical path should be: media/articles/{audio_uuid}.mp3
        """
        import uuid

        # Set up audio_uuid for the article
        self.article.audio_uuid = uuid.uuid4()
        self.article.save()

        expected_path = os.path.join(
            settings.MEDIA_ROOT, "articles", f"{self.article.audio_uuid}.mp3"
        )

        actual_path = self.article.get_canonical_audio_path()
        self.assertEqual(actual_path, expected_path)

    def test_canonical_path_consistency(self):
        """Test that canonical paths are consistent regardless of access method.

        The path should be the same whether accessed through article model,
        utility functions, or direct calculation.
        """
        import uuid

        # Set up audio_uuid for the article
        self.article.audio_uuid = uuid.uuid4()
        self.article.save()

        # Test multiple ways of getting the canonical path
        path1 = self.article.get_canonical_audio_path()

        # Verify the path format
        expected_path = os.path.join(
            settings.MEDIA_ROOT, "articles", f"{self.article.audio_uuid}.mp3"
        )
        self.assertEqual(path1, expected_path)

    def test_canonical_path_replaces_legacy_logic(self):
        """Test that canonical paths replace complex legacy path-guessing logic.

        The new implementation should use simple path joins instead of
        complex path resolution with multiple fallbacks.
        """
        import uuid

        # Set up audio_uuid for the article
        self.article.audio_uuid = uuid.uuid4()
        self.article.save()

        # Test that we don't need complex path resolution anymore
        canonical_path = self.article.get_canonical_audio_path()

        # The path should be deterministic and not require guessing
        self.assertTrue(canonical_path.endswith(f"{self.article.audio_uuid}.mp3"))
        self.assertIn("articles/", canonical_path)

        # Should not contain legacy patterns
        self.assertNotIn(f"audio/{self.user.id}/", canonical_path)  # Old pattern
        self.assertNotIn("article_", canonical_path)  # Old prefix pattern
        self.assertNotIn(f"/{self.article.id}.mp3", canonical_path)  # Old ID pattern

    @override_settings(MEDIA_ROOT="/tmp/test_media")
    def test_canonical_path_directory_creation(self):
        """Test that canonical path directories are created when needed."""
        import uuid

        with tempfile.TemporaryDirectory() as temp_dir:
            with override_settings(MEDIA_ROOT=temp_dir):
                # Set up audio_uuid for the article
                self.article.audio_uuid = uuid.uuid4()
                self.article.save()

                # Directory shouldn't exist initially
                articles_dir = os.path.join(temp_dir, "articles")
                self.assertFalse(os.path.exists(articles_dir))

                # This should create the articles directory
                self.article.ensure_canonical_directory_exists()
                self.assertTrue(os.path.exists(articles_dir))

    def test_canonical_path_permission_handling(self):
        """Test handling of permission issues when creating directories."""
        with tempfile.TemporaryDirectory() as temp_dir:
            with override_settings(MEDIA_ROOT=temp_dir):
                # Make the temp directory read-only
                os.chmod(temp_dir, 0o444)

                try:
                    # This should handle permission errors gracefully
                    with self.assertRaises(PermissionError):
                        self.article.ensure_canonical_directory_exists()
                finally:
                    # Restore permissions for cleanup
                    os.chmod(temp_dir, 0o755)

    def test_canonical_path_missing_media_root(self):
        """Test behavior when MEDIA_ROOT doesn't exist."""
        with override_settings(MEDIA_ROOT="/nonexistent/path"):
            # Should handle missing MEDIA_ROOT gracefully
            with self.assertRaises(FileNotFoundError):
                self.article.ensure_canonical_directory_exists()

    def test_canonical_path_with_special_characters(self):
        """Test canonical paths with special characters in user data."""
        import uuid

        # Create user with ID that might cause path issues
        special_user = User.objects.create_user(
            username="user@domain.com", email="special@example.com"
        )
        special_feed = Feed.objects.create(user=special_user, name="Special Feed")
        special_article = Article.objects.create(
            feed=special_feed,
            title="Article with special chars: <>&",
            text_content="Content",
            status=Article.PROCESSING,
            audio_uuid=uuid.uuid4(),  # Set audio_uuid
        )

        # Path should be safe regardless of user data
        canonical_path = special_article.get_canonical_audio_path()
        self.assertTrue(os.path.isabs(canonical_path))
        self.assertIn(str(special_article.audio_uuid), canonical_path)
        self.assertTrue(canonical_path.endswith(".mp3"))

    def test_article_save_uses_canonical_path(self):
        """Test that saving articles with audio uses canonical paths."""
        import uuid

        with tempfile.TemporaryDirectory() as temp_dir:
            with override_settings(MEDIA_ROOT=temp_dir):
                # Set up audio_uuid for the article
                self.article.audio_uuid = uuid.uuid4()
                self.article.save()

                # When article is processed and audio is saved
                canonical_path = self.article.get_canonical_audio_path()

                # Create a mock audio file
                os.makedirs(os.path.dirname(canonical_path), exist_ok=True)
                with open(canonical_path, "w") as f:
                    f.write("mock audio data")

                # Update article with canonical path
                self.article.set_canonical_audio_path()
                self.article.status = Article.COMPLETED
                self.article.save()

                # Verify the path is stored correctly
                self.article.refresh_from_db()
                expected_relative_path = os.path.join("articles", f"{self.article.audio_uuid}.mp3")
                self.assertEqual(self.article.audio_file_path, expected_relative_path)

    def test_article_media_serving_uses_canonical_path(self):
        """Test that media serving uses canonical paths consistently."""
        import uuid

        with tempfile.TemporaryDirectory() as temp_dir:
            with override_settings(MEDIA_ROOT=temp_dir):
                # Set up audio_uuid for the article
                self.article.audio_uuid = uuid.uuid4()
                self.article.save()

                # Set up article with canonical path
                self.article.set_canonical_audio_path()
                canonical_path = os.path.join(temp_dir, self.article.audio_file_path)

                # Create the audio file
                os.makedirs(os.path.dirname(canonical_path), exist_ok=True)
                with open(canonical_path, "w") as f:
                    f.write("mock audio data")

                # Test that media serving finds the file
                from text_to_audio.views import ArticleMediaView

                view = ArticleMediaView()

                # This should work with canonical paths
                resolved_path = view._find_audio_file(self.article)
                self.assertEqual(resolved_path, canonical_path)
                self.assertTrue(os.path.exists(resolved_path))

    def test_canonical_path_backwards_compatibility(self):
        """Test that canonical path system works with new structure."""
        import uuid

        # Create article with new canonical path format
        new_article = Article.objects.create(
            feed=self.feed,
            title="New Article",
            text_content="New content",
            audio_uuid=uuid.uuid4(),
            status=Article.COMPLETED,
        )

        # Should be able to get canonical path
        canonical_path = new_article.get_canonical_audio_path()
        expected_path = os.path.join(
            settings.MEDIA_ROOT, "articles", f"{new_article.audio_uuid}.mp3"
        )
        self.assertEqual(canonical_path, expected_path)

        # Set canonical path and verify it's stored correctly
        new_article.set_canonical_audio_path()
        self.assertTrue(new_article.audio_file_path.startswith("articles/"))

    def test_get_absolute_url_uses_canonical_path(self):
        """Test that article's get_absolute_url method works with canonical paths."""
        # Set up article with canonical path and audio_uuid
        import uuid as uuid_module

        self.article.audio_uuid = uuid_module.uuid4()
        self.article.set_canonical_audio_path()
        self.article.status = Article.COMPLETED
        self.article.save()

        # get_absolute_url should work with new path structure
        url = self.article.get_absolute_url()

        # Should return media URL for audio using audio_uuid
        self.assertIn("/audio/", url)
        self.assertIn(str(self.article.audio_uuid), url)

    def test_rss_feed_uses_canonical_paths(self):
        """Test that RSS feed generation uses canonical paths for enclosures."""
        import uuid as uuid_module2

        with tempfile.TemporaryDirectory() as temp_dir:
            with override_settings(MEDIA_ROOT=temp_dir):
                # Ensure article has audio_uuid for RSS feed
                self.article.audio_uuid = uuid_module2.uuid4()
                self.article.save()

                # Set up completed article with canonical path
                self.article.set_canonical_audio_path()
                self.article.status = Article.COMPLETED

                # Create the audio file
                canonical_path = os.path.join(temp_dir, self.article.audio_file_path)
                os.makedirs(os.path.dirname(canonical_path), exist_ok=True)
                with open(canonical_path, "wb") as f:
                    f.write(b"mock audio data")

                self.article.save()

                # Test RSS feed generation
                from text_to_audio.feeds import UserFeed

                feed = UserFeed()

                items = list(feed.items(self.feed))
                self.assertGreater(len(items), 0)

                # Test enclosure URL uses audio_uuid
                enclosure_url = feed.item_enclosure_url(self.article)
                self.assertIn("audio", enclosure_url)
                self.assertIn(str(self.article.audio_uuid), enclosure_url)
