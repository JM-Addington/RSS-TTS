"""Tests for article regeneration functionality."""

from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from text_to_audio.models import Article, Feed


class ArticleRegenerateViewTest(TestCase):
    """Test the article regeneration view."""

    def setUp(self):
        """Set up test data."""
        # Create test users
        self.user = User.objects.create_user(username="testuser", password="testpass")
        self.other_user = User.objects.create_user(
            username="otheruser", password="otherpass"
        )

        # Create feeds
        self.feed = Feed.objects.create(user=self.user, name="Test Feed")
        self.other_feed = Feed.objects.create(user=self.other_user, name="Other Feed")

        # Create test articles
        self.completed_article = Article.objects.create(
            feed=self.feed,
            title="Completed Article",
            source_url="https://example.com/article1",
            text_content="This is the content of the completed article.",
            status=Article.COMPLETED,
            audio_file_path="path/to/audio.mp3",
        )

        self.failed_article = Article.objects.create(
            feed=self.feed,
            title="Failed Article",
            text_content="This is the content of the failed article.",
            status=Article.FAILED,
            error_message="Failed to process",
        )

        self.processing_article = Article.objects.create(
            feed=self.feed,
            title="Processing Article",
            source_url="https://example.com/article2",
            status=Article.PROCESSING,
        )

        self.other_user_article = Article.objects.create(
            feed=self.other_feed,
            title="Other User Article",
            text_content="This belongs to another user.",
            status=Article.COMPLETED,
        )

    def test_login_required(self):
        """Test that login is required to regenerate articles."""
        url = reverse("article-regenerate", kwargs={"pk": self.completed_article.pk})
        response = self.client.post(url)
        self.assertEqual(response.status_code, 302)
        # Check redirect contains login
        login_url = reverse("login")
        self.assertIn(login_url, response.get("Location", ""))

    def test_user_can_only_regenerate_own_articles(self):
        """Test that users can only regenerate their own articles."""
        self.client.login(username="testuser", password="testpass")
        url = reverse("article-regenerate", kwargs={"pk": self.other_user_article.pk})
        response = self.client.post(url)
        self.assertEqual(response.status_code, 404)

    @patch("text_to_audio.views.process_article.delay")
    def test_regenerate_completed_article(self, mock_process_article):
        """Test regenerating a completed article."""
        self.client.login(username="testuser", password="testpass")
        original_pk = self.completed_article.pk
        original_title = self.completed_article.title
        original_content = self.completed_article.text_content
        original_url = self.completed_article.source_url

        url = reverse("article-regenerate", kwargs={"pk": original_pk})
        response = self.client.post(url)

        # Check redirect
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.get("Location"), reverse("article-list"))

        # Check original article is deleted
        self.assertFalse(Article.objects.filter(pk=original_pk).exists())

        # Check new article is created with same content
        new_article = Article.objects.get(
            feed=self.feed, title=original_title, text_content=original_content
        )
        self.assertEqual(new_article.source_url, original_url)
        self.assertEqual(new_article.status, Article.PROCESSING)
        self.assertEqual(new_article.audio_file_path, "")
        self.assertIsNone(new_article.error_message)

        # Check that process_article was called with new article ID
        mock_process_article.assert_called_once_with(new_article.pk)

    @patch("text_to_audio.views.process_article.delay")
    def test_regenerate_failed_article(self, mock_process_article):
        """Test regenerating a failed article."""
        self.client.login(username="testuser", password="testpass")
        original_pk = self.failed_article.pk

        url = reverse("article-regenerate", kwargs={"pk": original_pk})
        response = self.client.post(url)

        # Check redirect
        self.assertEqual(response.status_code, 302)

        # Check original article is deleted
        self.assertFalse(Article.objects.filter(pk=original_pk).exists())

        # Check new article is created and processing
        new_article = Article.objects.get(
            feed=self.feed, title=self.failed_article.title
        )
        self.assertEqual(new_article.status, Article.PROCESSING)
        self.assertIsNone(new_article.error_message)

        # Check that process_article was called
        mock_process_article.assert_called_once_with(new_article.pk)

    @patch("text_to_audio.views.process_article.delay")
    def test_regenerate_processing_article(self, mock_process_article):
        """Test regenerating an article that's currently processing."""
        self.client.login(username="testuser", password="testpass")
        original_pk = self.processing_article.pk

        url = reverse("article-regenerate", kwargs={"pk": original_pk})
        response = self.client.post(url)

        # Should still work - delete and recreate
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Article.objects.filter(pk=original_pk).exists())

        # Check new article is created
        new_article = Article.objects.get(
            feed=self.feed, title=self.processing_article.title
        )
        mock_process_article.assert_called_once_with(new_article.pk)

    def test_regenerate_nonexistent_article(self):
        """Test regenerating a non-existent article returns 404."""
        self.client.login(username="testuser", password="testpass")
        url = reverse("article-regenerate", kwargs={"pk": 99999})
        response = self.client.post(url)
        self.assertEqual(response.status_code, 404)

    def test_regenerate_only_accepts_post(self):
        """Test that regenerate view only accepts POST requests."""
        self.client.login(username="testuser", password="testpass")
        url = reverse("article-regenerate", kwargs={"pk": self.completed_article.pk})

        # GET should not be allowed
        response = self.client.get(url)
        self.assertEqual(response.status_code, 405)  # Method Not Allowed

    @patch("text_to_audio.views.process_article.delay")
    def test_regenerate_preserves_all_fields(self, mock_process_article):
        """Test that regeneration preserves all original article fields."""
        self.client.login(username="testuser", password="testpass")

        # Create an article with all fields populated
        article = Article.objects.create(
            feed=self.feed,
            title="Full Article",
            source_url="https://example.com/full",
            text_content="Full content with all fields.",
            status=Article.COMPLETED,
        )

        url = reverse("article-regenerate", kwargs={"pk": article.pk})
        self.client.post(url)

        # Check new article has all fields preserved
        new_article = Article.objects.get(feed=self.feed, title="Full Article")
        self.assertEqual(new_article.source_url, "https://example.com/full")
        self.assertEqual(new_article.text_content, "Full content with all fields.")
        self.assertEqual(new_article.feed, self.feed)
        self.assertEqual(new_article.status, Article.PROCESSING)
