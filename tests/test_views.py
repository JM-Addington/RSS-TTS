"""Tests for the text_to_audio app views."""

# mypy: ignore-errors

import uuid
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from text_to_audio.models import Article, Feed

User = get_user_model()


class RegenerateArticleViewTest(TestCase):
    """Tests for the RegenerateArticleView."""

    def setUp(self):
        """Set up test data."""
        self.client = Client()
        self.user = User.objects.create_user(
            username="testuser", password="testpassword", email="test@example.com"
        )
        self.feed = Feed.objects.create(user=self.user, name="Test Feed")
        self.article = Article.objects.create(
            feed=self.feed,
            title="Test Article",
            text_content="This is a test article.",
            status=Article.COMPLETED,
            audio_uuid=uuid.uuid4(),
        )
        self.client.login(username="testuser", password="testpassword")

    @mock.patch("text_to_audio.views.process_article.delay")
    def test_regenerate_article(self, mock_process_article):
        """Test regenerating an article creates a new article and queues processing."""
        # Get the initial article count
        initial_count = Article.objects.count()

        # Make the post request to regenerate
        response = self.client.post(
            reverse("article-regenerate", kwargs={"article_id": self.article.pk})
        )

        # Check that we were redirected to the feed articles page
        self.assertRedirects(
            response, reverse("feed-articles", kwargs={"feed_id": self.feed.pk})
        )

        # Check that a new article was created
        self.assertEqual(Article.objects.count(), initial_count + 1)

        # Get the new article
        new_article = Article.objects.exclude(pk=self.article.pk).first()

        # Check that the new article has the correct properties
        self.assertEqual(new_article.feed, self.article.feed)
        self.assertEqual(new_article.title, self.article.title)
        self.assertEqual(new_article.text_content, self.article.text_content)
        self.assertEqual(new_article.status, Article.PROCESSING)

        # Check that the new article has a different UUID
        self.assertIsNotNone(new_article.audio_uuid)
        self.assertNotEqual(new_article.audio_uuid, self.article.audio_uuid)

        # Check that process_article.delay was called with the new article's ID
        mock_process_article.assert_called_once_with(new_article.pk)

    def test_regenerate_article_access_control(self):
        """Test that users can only regenerate their own articles."""
        # Create another user and article
        other_user = User.objects.create_user(
            username="otheruser", password="otherpassword", email="other@example.com"
        )
        other_feed = Feed.objects.create(user=other_user, name="Other Feed")
        other_article = Article.objects.create(
            feed=other_feed,
            title="Other Article",
            text_content="This is another test article.",
            status=Article.COMPLETED,
            audio_uuid=uuid.uuid4(),
        )

        # Try to regenerate the other user's article
        response = self.client.post(
            reverse("article-regenerate", kwargs={"article_id": other_article.pk})
        )

        # Should return 404 since the user doesn't own the article
        self.assertEqual(response.status_code, 404)

        # Make sure no new article was created
        self.assertEqual(Article.objects.filter(feed=other_feed).count(), 1)
