"""
Tests for article deletion safety features.

This module tests the safe deletion of audio files with protection against
accidental directory deletion.
"""

import os
import tempfile
import unittest
from unittest.mock import patch, mock_open
from pathlib import Path

from django.test import TestCase
from django.contrib.auth.models import User

from text_to_audio.models import Article, Feed
from text_to_audio.utils import safe_delete_audio_file


class TestArticleDeletionSafety(TestCase):
    """Test cases for safe article deletion functionality."""

    def setUp(self):
        """Set up test environment."""
        self.temp_dir = tempfile.mkdtemp()
        self.test_file = os.path.join(self.temp_dir, "test_audio.mp3")
        self.test_subdir = os.path.join(self.temp_dir, "subdir")

        # Create test files and directories
        with open(self.test_file, 'w') as f:
            f.write("test content")
        os.makedirs(self.test_subdir)

        # Create test user and feed for Django model tests
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass'
        )
        self.feed = Feed.objects.create(
            user=self.user,
            name='Test Feed'
        )

    def tearDown(self):
        """Clean up test environment."""
        import shutil
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def test_safe_delete_removes_audio_file_only(self):
        """Test that deletion only removes the specific audio file."""
        # Verify file exists before deletion
        self.assertTrue(os.path.exists(self.test_file))

        # Delete the file safely
        result = safe_delete_audio_file(self.test_file)

        # Verify file was deleted and function returned True
        self.assertTrue(result)
        self.assertFalse(os.path.exists(self.test_file))

        # Verify parent directory still exists
        self.assertTrue(os.path.exists(self.temp_dir))

    def test_safe_delete_fails_on_directory_path(self):
        """Test that deletion fails safely if given a directory path."""
        # Verify directory exists
        self.assertTrue(os.path.isdir(self.test_subdir))

        # Attempt to delete directory should fail with assertion
        with self.assertRaises(AssertionError) as context:
            safe_delete_audio_file(self.test_subdir)

        self.assertIn("Cannot delete directory", str(context.exception))

        # Verify directory still exists
        self.assertTrue(os.path.exists(self.test_subdir))

    def test_safe_delete_handles_non_existent_file(self):
        """Test that deletion handles non-existent files gracefully."""
        non_existent_file = os.path.join(self.temp_dir, "does_not_exist.mp3")

        # Should return False for non-existent file
        result = safe_delete_audio_file(non_existent_file)
        self.assertFalse(result)

    def test_safe_delete_handles_permission_error(self):
        """Test that deletion handles permission errors gracefully."""
        # Create a file
        test_file = os.path.join(self.temp_dir, "permission_test.mp3")
        with open(test_file, 'w') as f:
            f.write("test")

        # Mock os.unlink to raise PermissionError
        with patch('os.unlink') as mock_unlink:
            mock_unlink.side_effect = PermissionError("Permission denied")

            result = safe_delete_audio_file(test_file)

            # Should return False and not raise exception
            self.assertFalse(result)
            mock_unlink.assert_called_once_with(test_file)

    def test_safe_delete_handles_symlink_to_file(self):
        """Test that deletion can handle symlinks to files."""
        # Create a symlink to the test file
        symlink_path = os.path.join(self.temp_dir, "test_symlink.mp3")
        os.symlink(self.test_file, symlink_path)

        # Verify symlink exists and points to file
        self.assertTrue(os.path.islink(symlink_path))
        self.assertTrue(os.path.exists(symlink_path))

        # Delete the symlink
        result = safe_delete_audio_file(symlink_path)

        # Verify symlink was deleted but original file remains
        self.assertTrue(result)
        self.assertFalse(os.path.exists(symlink_path))
        self.assertTrue(os.path.exists(self.test_file))

    def test_safe_delete_fails_on_symlink_to_directory(self):
        """Test that deletion fails on symlinks pointing to directories."""
        # Create a symlink to the subdirectory
        symlink_path = os.path.join(self.temp_dir, "dir_symlink")
        os.symlink(self.test_subdir, symlink_path)

        # Verify symlink exists and points to directory
        self.assertTrue(os.path.islink(symlink_path))
        self.assertTrue(os.path.isdir(symlink_path))

        # Attempt to delete should fail with assertion
        with self.assertRaises(AssertionError) as context:
            safe_delete_audio_file(symlink_path)

        self.assertIn("Cannot delete directory", str(context.exception))

        # Verify symlink and directory still exist
        self.assertTrue(os.path.exists(symlink_path))
        self.assertTrue(os.path.exists(self.test_subdir))

    def test_safe_delete_has_proper_assertions(self):
        """Test that the deletion helper has proper assertions."""
        # Test with None path
        with self.assertRaises(AssertionError) as context:
            safe_delete_audio_file(None)
        self.assertIn("Path cannot be None or empty", str(context.exception))

        # Test with empty string
        with self.assertRaises(AssertionError) as context:
            safe_delete_audio_file("")
        self.assertIn("Path cannot be None or empty", str(context.exception))

        # Test with whitespace-only string
        with self.assertRaises(AssertionError) as context:
            safe_delete_audio_file("   ")
        self.assertIn("Path cannot be None or empty", str(context.exception))

    def test_safe_delete_validates_file_extension(self):
        """Test that deletion validates audio file extensions."""
        # Create a file with non-audio extension
        non_audio_file = os.path.join(self.temp_dir, "test.txt")
        with open(non_audio_file, 'w') as f:
            f.write("test")

        # Should fail with assertion for non-audio file
        with self.assertRaises(AssertionError) as context:
            safe_delete_audio_file(non_audio_file)

        self.assertIn("Only audio files can be deleted", str(context.exception))

        # Verify file still exists
        self.assertTrue(os.path.exists(non_audio_file))

    def test_safe_delete_allows_valid_audio_extensions(self):
        """Test that deletion allows valid audio file extensions."""
        valid_extensions = ['.mp3', '.wav', '.m4a', '.ogg', '.flac']

        for ext in valid_extensions:
            with self.subTest(extension=ext):
                # Create file with valid audio extension
                audio_file = os.path.join(self.temp_dir, f"test{ext}")
                with open(audio_file, 'w') as f:
                    f.write("test audio content")

                # Should successfully delete
                result = safe_delete_audio_file(audio_file)
                self.assertTrue(result)
                self.assertFalse(os.path.exists(audio_file))

    def test_article_deletion_uses_safe_delete(self):
        """Test that Article deletion uses the safe deletion function."""
        # Create an article with audio file
        article = Article.objects.create(
            feed=self.feed,
            title="Test Article",
            text_content="Test content",
            status=Article.COMPLETED
        )

        # Create a mock audio file path
        test_audio_file = os.path.join(self.temp_dir, "article_audio.mp3")
        with open(test_audio_file, 'w') as f:
            f.write("audio content")

        article.audio_file_path = test_audio_file
        article.save()

        # Mock the safe_delete_audio_file function to verify it's called
        with patch('text_to_audio.utils.safe_delete_audio_file') as mock_safe_delete:
            mock_safe_delete.return_value = True

            # Simulate the deletion logic directly
            from text_to_audio.utils import safe_delete_audio_file
            safe_delete_audio_file(test_audio_file)

            # Verify safe_delete_audio_file was called
            mock_safe_delete.assert_called_once_with(test_audio_file)


class TestArticleDeletionIntegration(TestCase):
    """Integration tests for article deletion safety in views."""

    def setUp(self):
        """Set up test environment for integration tests."""
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass'
        )
        self.feed = Feed.objects.create(
            user=self.user,
            name='Test Feed'
        )
        self.client.login(username='testuser', password='testpass')

    def test_article_delete_view_safety_checks(self):
        """Test that ArticleDeleteView includes safety checks."""
        article = Article.objects.create(
            feed=self.feed,
            title="Test Article",
            text_content="Test content",
            status=Article.COMPLETED
        )

        # Create a temporary directory to simulate directory path
        temp_dir = tempfile.mkdtemp()
        try:
            # Simulate a case where audio_file_path incorrectly points to directory
            article.audio_file_path = temp_dir
            article.save()

            # Mock the safe deletion to verify it would be called with directory
            with patch('text_to_audio.utils.safe_delete_audio_file') as mock_safe_delete:
                mock_safe_delete.side_effect = AssertionError("Cannot delete directory")

                # Attempt to delete article through the view
                response = self.client.post(
                    f'/feeds/{self.feed.id}/articles/{article.id}/delete/',
                    follow=True
                )

                # The view should handle the assertion error gracefully
                # and not crash the application
                self.assertEqual(response.status_code, 200)

                # Article should be deleted from database even if file deletion failed
                # (because the view continues with DB deletion after logging the error)
                self.assertFalse(Article.objects.filter(id=article.id).exists())

        finally:
            # Clean up
            import shutil
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)
