"""Tests for audio path migration command.

This module tests the migration command that moves legacy audio files
to the new canonical location and updates database paths accordingly.
"""

import os
import tempfile
import uuid
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from django.test.utils import captured_stderr, captured_stdout

from text_to_audio.models import Article, Feed

User = get_user_model()


class MigrateAudioPathsTestCase(TestCase):
    """Test cases for the audio path migration command."""

    def setUp(self):
        """Set up test data."""
        self.user1 = User.objects.create_user(
            username="user1", email="user1@example.com", password="testpass123"
        )
        self.user2 = User.objects.create_user(
            username="user2", email="user2@example.com", password="testpass123"
        )

        self.feed1 = Feed.objects.create(user=self.user1, name="Feed 1")
        self.feed2 = Feed.objects.create(user=self.user2, name="Feed 2")

        # Create articles with different legacy path formats
        self.article1 = Article.objects.create(
            feed=self.feed1,
            title="Article 1",
            text_content="Content 1",
            audio_uuid=uuid.uuid4(),
            audio_file_path=f"audio/{self.user1.id}/article_{uuid.uuid4()}.mp3",  # Legacy format
            status=Article.COMPLETED,
        )

        self.article2 = Article.objects.create(
            feed=self.feed1,
            title="Article 2",
            text_content="Content 2",
            audio_uuid=uuid.uuid4(),
            audio_file_path=f"articles/{self.user1.id}/{self.feed1.id}/article_{uuid.uuid4()}.mp3",
            status=Article.COMPLETED,
        )

        self.article3 = Article.objects.create(
            feed=self.feed2,
            title="Article 3",
            text_content="Content 3",
            audio_uuid=uuid.uuid4(),
            audio_file_path="",  # No path set
            status=Article.PROCESSING,
        )

    def test_migration_command_exists(self):
        """Test that the migrate_audio_paths management command exists."""
        # This should fail initially until command is created
        try:
            call_command("migrate_audio_paths", "--dry-run")
        except CommandError as e:
            if "Unknown command" in str(e):
                self.fail("migrate_audio_paths management command does not exist")

    def test_identify_legacy_files(self):
        """Test that migration command correctly identifies legacy audio files."""
        with tempfile.TemporaryDirectory() as temp_dir:
            with override_settings(MEDIA_ROOT=temp_dir):
                # Create legacy file structure
                legacy_file1 = os.path.join(temp_dir, self.article1.audio_file_path)
                legacy_file2 = os.path.join(temp_dir, self.article2.audio_file_path)

                os.makedirs(os.path.dirname(legacy_file1), exist_ok=True)
                os.makedirs(os.path.dirname(legacy_file2), exist_ok=True)

                with open(legacy_file1, "w") as f:
                    f.write("mock audio 1")
                with open(legacy_file2, "w") as f:
                    f.write("mock audio 2")

                # Run migration in dry-run mode
                with captured_stdout() as stdout:
                    call_command("migrate_audio_paths", "--dry-run")

                output = stdout.getvalue()

                # Should identify both legacy files
                self.assertIn("Found 2 articles to migrate", output)
                self.assertIn(f"Article {self.article1.id}:", output)
                self.assertIn(f"Article {self.article2.id}:", output)
                # Should not include processing article without file
                self.assertNotIn(f"Article {self.article3.id}:", output)

    def test_migrate_files_to_canonical_location(self):
        """Test that files are moved to the new canonical location."""
        with tempfile.TemporaryDirectory() as temp_dir:
            with override_settings(MEDIA_ROOT=temp_dir):
                # Create legacy file
                legacy_file = os.path.join(temp_dir, self.article1.audio_file_path)
                os.makedirs(os.path.dirname(legacy_file), exist_ok=True)

                with open(legacy_file, "w") as f:
                    f.write("mock audio content")

                # Verify legacy file exists
                self.assertTrue(os.path.exists(legacy_file))

                # Run migration
                call_command("migrate_audio_paths")

                # Verify file moved to canonical location
                canonical_path = os.path.join(
                    temp_dir, "articles", f"{self.article1.audio_uuid}.mp3"
                )
                self.assertTrue(os.path.exists(canonical_path))

                # Verify content preserved
                with open(canonical_path, "r") as f:
                    self.assertEqual(f.read(), "mock audio content")

                # Verify legacy file removed
                self.assertFalse(os.path.exists(legacy_file))

    def test_update_database_paths(self):
        """Test that database paths are updated correctly after migration."""
        with tempfile.TemporaryDirectory() as temp_dir:
            with override_settings(MEDIA_ROOT=temp_dir):
                # Create legacy file
                legacy_file = os.path.join(temp_dir, self.article1.audio_file_path)
                os.makedirs(os.path.dirname(legacy_file), exist_ok=True)

                with open(legacy_file, "w") as f:
                    f.write("mock audio content")

                # Store original path
                original_path = self.article1.audio_file_path

                # Run migration
                call_command("migrate_audio_paths")

                # Refresh from database
                self.article1.refresh_from_db()

                # Verify path updated to canonical format
                expected_path = f"articles/{self.article1.audio_uuid}.mp3"
                self.assertEqual(self.article1.audio_file_path, expected_path)
                self.assertNotEqual(self.article1.audio_file_path, original_path)

    def test_migration_handles_missing_files(self):
        """Test migration gracefully handles articles with missing audio files."""
        with tempfile.TemporaryDirectory() as temp_dir:
            with override_settings(MEDIA_ROOT=temp_dir):
                # Don't create the actual file - simulate missing file

                with captured_stderr() as stderr:
                    call_command("migrate_audio_paths")

                error_output = stderr.getvalue()

                # Should log warning about missing file
                self.assertIn("Audio file not found", error_output)
                self.assertIn(str(self.article1.id), error_output)

                # Article path should remain unchanged
                self.article1.refresh_from_db()
                self.assertTrue(self.article1.audio_file_path.startswith("articles/"))

    def test_migration_handles_permission_errors(self):
        """Test migration handles permission errors gracefully."""
        with tempfile.TemporaryDirectory() as temp_dir:
            with override_settings(MEDIA_ROOT=temp_dir):
                # Create legacy file
                legacy_file = os.path.join(temp_dir, self.article1.audio_file_path)
                os.makedirs(os.path.dirname(legacy_file), exist_ok=True)

                with open(legacy_file, "w") as f:
                    f.write("mock audio content")

                # Make destination directory read-only
                articles_dir = os.path.join(temp_dir, "articles")
                os.makedirs(articles_dir, exist_ok=True)
                os.chmod(articles_dir, 0o444)

                try:
                    with captured_stderr() as stderr:
                        call_command("migrate_audio_paths")

                    error_output = stderr.getvalue()

                    # Should handle permission error gracefully
                    self.assertIn("Permission denied", error_output)
                    self.assertIn(str(self.article1.id), error_output)

                    # Original file should still exist
                    self.assertTrue(os.path.exists(legacy_file))

                finally:
                    # Restore permissions for cleanup
                    os.chmod(articles_dir, 0o755)

    def test_migration_rollback_on_error(self):
        """Test migration rollback when errors occur during batch processing."""
        with tempfile.TemporaryDirectory() as temp_dir:
            with override_settings(MEDIA_ROOT=temp_dir):
                # Create files for both articles
                legacy_file1 = os.path.join(temp_dir, self.article1.audio_file_path)
                legacy_file2 = os.path.join(temp_dir, self.article2.audio_file_path)

                os.makedirs(os.path.dirname(legacy_file1), exist_ok=True)
                os.makedirs(os.path.dirname(legacy_file2), exist_ok=True)

                with open(legacy_file1, "w") as f:
                    f.write("mock audio 1")
                with open(legacy_file2, "w") as f:
                    f.write("mock audio 2")

                # Mock a database error during the second migration
                with patch("text_to_audio.models.Article.save") as mock_save:
                    mock_save.side_effect = [None, Exception("Database error")]

                    with captured_stderr() as stderr:
                        with self.assertRaises(CommandError):
                            call_command("migrate_audio_paths", "--rollback-on-error")

                    error_output = stderr.getvalue()

                    # Should indicate rollback occurred
                    self.assertIn("Rolling back", error_output)

                    # Files should be restored to original locations
                    self.assertTrue(os.path.exists(legacy_file1))
                    self.assertTrue(os.path.exists(legacy_file2))

    def test_migration_dry_run_mode(self):
        """Test that dry-run mode doesn't actually move files or update database."""
        with tempfile.TemporaryDirectory() as temp_dir:
            with override_settings(MEDIA_ROOT=temp_dir):
                # Create legacy file
                legacy_file = os.path.join(temp_dir, self.article1.audio_file_path)
                os.makedirs(os.path.dirname(legacy_file), exist_ok=True)

                with open(legacy_file, "w") as f:
                    f.write("mock audio content")

                original_path = self.article1.audio_file_path

                # Run dry-run migration
                with captured_stdout() as stdout:
                    call_command("migrate_audio_paths", "--dry-run")

                output = stdout.getvalue()

                # Should show what would be done
                self.assertIn("Would migrate", output)
                self.assertIn(str(self.article1.id), output)

                # File should still be in original location
                self.assertTrue(os.path.exists(legacy_file))

                # Database should be unchanged
                self.article1.refresh_from_db()
                self.assertEqual(self.article1.audio_file_path, original_path)

                # Canonical location should not exist
                canonical_path = os.path.join(
                    temp_dir, "articles", f"{self.article1.audio_uuid}.mp3"
                )
                self.assertFalse(os.path.exists(canonical_path))

    def test_migration_with_force_flag(self):
        """Test migration with force flag overwrites existing canonical files."""
        with tempfile.TemporaryDirectory() as temp_dir:
            with override_settings(MEDIA_ROOT=temp_dir):
                # Create legacy file
                legacy_file = os.path.join(temp_dir, self.article1.audio_file_path)
                os.makedirs(os.path.dirname(legacy_file), exist_ok=True)

                with open(legacy_file, "w") as f:
                    f.write("new content")

                # Create existing file at canonical location
                canonical_path = os.path.join(
                    temp_dir, "articles", f"{self.article1.audio_uuid}.mp3"
                )
                os.makedirs(os.path.dirname(canonical_path), exist_ok=True)

                with open(canonical_path, "w") as f:
                    f.write("old content")

                # Run migration with force
                call_command("migrate_audio_paths", "--force")

                # Should overwrite existing file
                with open(canonical_path, "r") as f:
                    self.assertEqual(f.read(), "new content")

                # Legacy file should be removed
                self.assertFalse(os.path.exists(legacy_file))

    def test_migration_without_force_skips_existing(self):
        """Test migration without force flag skips existing canonical files."""
        with tempfile.TemporaryDirectory() as temp_dir:
            with override_settings(MEDIA_ROOT=temp_dir):
                # Create legacy file
                legacy_file = os.path.join(temp_dir, self.article1.audio_file_path)
                os.makedirs(os.path.dirname(legacy_file), exist_ok=True)

                with open(legacy_file, "w") as f:
                    f.write("new content")

                # Create existing file at canonical location
                canonical_path = os.path.join(
                    temp_dir, "articles", f"{self.article1.audio_uuid}.mp3"
                )
                os.makedirs(os.path.dirname(canonical_path), exist_ok=True)

                with open(canonical_path, "w") as f:
                    f.write("old content")

                # Run migration without force
                with captured_stdout() as stdout:
                    call_command("migrate_audio_paths")

                output = stdout.getvalue()

                # Should skip existing file
                self.assertIn("already exists", output)

                # Existing file should be unchanged
                with open(canonical_path, "r") as f:
                    self.assertEqual(f.read(), "old content")

                # Legacy file should still exist
                self.assertTrue(os.path.exists(legacy_file))

    def test_migration_batch_processing(self):
        """Test migration processes articles in batches for performance."""
        # Create many articles for batch testing
        articles = []
        for i in range(25):  # Create more than typical batch size
            article = Article.objects.create(
                feed=self.feed1,
                title=f"Batch Article {i}",
                text_content=f"Content {i}",
                audio_uuid=uuid.uuid4(),
                audio_file_path=f"articles/{uuid.uuid4()}.mp3",
                status=Article.COMPLETED,
            )
            articles.append(article)

        with tempfile.TemporaryDirectory() as temp_dir:
            with override_settings(MEDIA_ROOT=temp_dir):
                # Create legacy files
                for article in articles:
                    legacy_file = os.path.join(temp_dir, article.audio_file_path)
                    os.makedirs(os.path.dirname(legacy_file), exist_ok=True)
                    with open(legacy_file, "w") as f:
                        f.write(f"content for {article.id}")

                # Run migration with small batch size
                with captured_stdout() as stdout:
                    call_command("migrate_audio_paths", "--batch-size=10")

                output = stdout.getvalue()

                # Should process in batches
                self.assertIn("Processing batch", output)

                # All files should be migrated
                for article in articles:
                    canonical_path = os.path.join(
                        temp_dir, "articles", f"{article.audio_uuid}.mp3"
                    )
                    self.assertTrue(os.path.exists(canonical_path))

    def test_migration_statistics_reporting(self):
        """Test that migration command reports statistics correctly."""
        with tempfile.TemporaryDirectory() as temp_dir:
            with override_settings(MEDIA_ROOT=temp_dir):
                # Create one successful file and one missing file
                legacy_file1 = os.path.join(temp_dir, self.article1.audio_file_path)
                os.makedirs(os.path.dirname(legacy_file1), exist_ok=True)
                with open(legacy_file1, "w") as f:
                    f.write("mock audio 1")

                # Don't create file for article2 (simulate missing)

                with captured_stdout() as stdout:
                    call_command("migrate_audio_paths")

                output = stdout.getvalue()

                # Should report statistics
                self.assertIn("Migration completed", output)
                self.assertIn("1 files migrated successfully", output)
                self.assertIn("1 files failed", output)
                self.assertIn("0 files skipped", output)

    def test_migration_preserves_file_metadata(self):
        """Test that migration preserves file timestamps and permissions."""
        with tempfile.TemporaryDirectory() as temp_dir:
            with override_settings(MEDIA_ROOT=temp_dir):
                # Create legacy file with specific timestamp and permissions
                legacy_file = os.path.join(temp_dir, self.article1.audio_file_path)
                os.makedirs(os.path.dirname(legacy_file), exist_ok=True)

                with open(legacy_file, "w") as f:
                    f.write("mock audio content")

                # Set specific permissions and modify time
                os.chmod(legacy_file, 0o644)
                original_stat = os.stat(legacy_file)

                # Run migration
                call_command("migrate_audio_paths")

                # Check canonical file
                canonical_path = os.path.join(
                    temp_dir, "articles", f"{self.article1.audio_uuid}.mp3"
                )
                self.assertTrue(os.path.exists(canonical_path))

                new_stat = os.stat(canonical_path)

                # Timestamps should be preserved (within reasonable tolerance)
                self.assertAlmostEqual(
                    original_stat.st_mtime, new_stat.st_mtime, delta=1
                )

                # Permissions should be preserved
                self.assertEqual(
                    original_stat.st_mode & 0o777, new_stat.st_mode & 0o777
                )
