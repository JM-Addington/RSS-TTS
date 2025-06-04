"""Test for RSS-TTS API endpoints."""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from text_to_audio.models import Article, Feed

User = get_user_model()


class APITestCase(TestCase):
    """Base test case for API tests."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass123"
        )
        self.other_user = User.objects.create_user(
            username="otheruser", email="other@example.com", password="testpass123"
        )

        self.feed = Feed.objects.create(user=self.user, name="Test Feed")
        self.other_feed = Feed.objects.create(
            user=self.other_user, name="Other User Feed"
        )

        self.client = APIClient()


class AuthenticationAPITests(APITestCase):
    """Test API authentication endpoints."""

    def test_create_api_token_authenticated(self):
        """Test creating API token for authenticated user."""
        self.client.force_authenticate(user=self.user)

        url = reverse("api:create-token")
        response = self.client.post(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("token", response.data)
        self.assertTrue(response.data["created"])

        # Verify token was created
        self.assertTrue(Token.objects.filter(user=self.user).exists())

    def test_create_api_token_unauthenticated(self):
        """Test creating API token fails for unauthenticated user."""
        url = reverse("api:create-token")
        response = self.client.post(url)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_create_api_token_idempotent(self):
        """Test that creating token multiple times returns same token."""
        self.client.force_authenticate(user=self.user)

        url = reverse("api:create-token")

        # First call creates token
        response1 = self.client.post(url)
        self.assertEqual(response1.status_code, status.HTTP_200_OK)
        self.assertTrue(response1.data["created"])
        token1 = response1.data["token"]

        # Second call returns existing token
        response2 = self.client.post(url)
        self.assertEqual(response2.status_code, status.HTTP_200_OK)
        self.assertFalse(response2.data["created"])
        token2 = response2.data["token"]

        self.assertEqual(token1, token2)

    def test_revoke_api_token(self):
        """Test revoking API token."""
        self.client.force_authenticate(user=self.user)

        # Create token first
        Token.objects.create(user=self.user)

        url = reverse("api:revoke-token")
        response = self.client.delete(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("revoked successfully", response.data["message"])

        # Verify token was deleted
        self.assertFalse(Token.objects.filter(user=self.user).exists())

    def test_revoke_nonexistent_token(self):
        """Test revoking token that doesn't exist."""
        self.client.force_authenticate(user=self.user)

        url = reverse("api:revoke-token")
        response = self.client.delete(url)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class TokenAuthenticationTests(APITestCase):
    """Test token-based authentication for API endpoints."""

    def setUp(self):
        """Set up test data with tokens."""
        super().setUp()
        self.token = Token.objects.create(user=self.user)

    def test_token_authentication_valid(self):
        """Test that valid token allows access."""
        self.client.credentials(HTTP_AUTHORIZATION="Token " + self.token.key)

        url = reverse("api:status")
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["user"], self.user.username)

    def test_token_authentication_invalid(self):
        """Test that invalid token denies access."""
        self.client.credentials(HTTP_AUTHORIZATION="Token invalidtoken")

        url = reverse("api:status")
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_no_authentication(self):
        """Test that endpoints require authentication."""
        url = reverse("api:status")
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class FeedAPITests(APITestCase):
    """Test Feed API endpoints."""

    def setUp(self):
        """Set up test data with authentication."""
        super().setUp()
        self.token = Token.objects.create(user=self.user)
        self.client.credentials(HTTP_AUTHORIZATION="Token " + self.token.key)

    def test_list_feeds(self):
        """Test listing user's feeds."""
        url = reverse("api:feed-list")
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 1)
        self.assertEqual(response.data["results"][0]["name"], self.feed.name)

        # Should not include other user's feeds
        feed_names = [feed["name"] for feed in response.data["results"]]
        self.assertNotIn(self.other_feed.name, feed_names)


class ArticleAPITests(APITestCase):
    """Test Article API endpoints."""

    def setUp(self):
        """Set up test data with authentication."""
        super().setUp()
        self.token = Token.objects.create(user=self.user)
        self.client.credentials(HTTP_AUTHORIZATION="Token " + self.token.key)

        self.article = Article.objects.create(
            feed=self.feed,
            title="Test Article",
            text_content="This is test content.",
            status=Article.COMPLETED,
        )

    def test_list_articles(self):
        """Test listing user's articles."""
        url = reverse("api:article-list")
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 1)
        self.assertEqual(response.data["results"][0]["title"], self.article.title)

    def test_list_articles_filtered_by_feed(self):
        """Test filtering articles by feed."""
        # Create another feed and article
        other_feed = Feed.objects.create(user=self.user, name="Other Feed")
        Article.objects.create(
            feed=other_feed, title="Other Article", text_content="Other content"
        )

        url = reverse("api:article-list")
        response = self.client.get(url, {"feed_id": self.feed.id})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 1)
        self.assertEqual(response.data["results"][0]["title"], self.article.title)

    def test_list_articles_filtered_by_status(self):
        """Test filtering articles by status."""
        # Create a processing article
        Article.objects.create(
            feed=self.feed,
            title="Processing Article",
            text_content="Processing content",
            status=Article.PROCESSING,
        )

        url = reverse("api:article-list")
        response = self.client.get(url, {"status": Article.COMPLETED})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 1)
        self.assertEqual(response.data["results"][0]["status"], Article.COMPLETED)

    def test_get_article_detail(self):
        """Test getting article details."""
        url = reverse("api:article-detail", kwargs={"id": self.article.id})
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["title"], self.article.title)
        self.assertEqual(response.data["feed_name"], self.feed.name)

    def test_get_article_detail_unauthorized(self):
        """Test getting article detail for unauthorized user."""
        other_token = Token.objects.create(user=self.other_user)
        self.client.credentials(HTTP_AUTHORIZATION="Token " + other_token.key)

        url = reverse("api:article-detail", kwargs={"id": self.article.id})
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    @patch("text_to_audio.tasks.process_article.delay")
    def test_create_article_with_text(self, mock_task):
        """Test creating article with text content."""
        mock_task.return_value.id = "test-task-id"

        url = reverse("api:article-create")
        data = {
            "feed_token": str(self.feed.token),
            "title": "New Article",
            "text_content": "This is new content for testing.",
        }

        response = self.client.post(url, data, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        mock_task.assert_called_once()

        # Verify article was created
        article = Article.objects.get(title="New Article")
        self.assertEqual(article.feed, self.feed)
        self.assertEqual(article.text_content, data["text_content"])
        self.assertEqual(article.celery_task_id, "test-task-id")

    @patch("text_to_audio.tasks.process_article.delay")
    def test_create_article_with_url(self, mock_task):
        """Test creating article with source URL."""
        mock_task.return_value.id = "test-task-id"

        url = reverse("api:article-create")
        data = {
            "feed_token": str(self.feed.token),
            "source_url": "https://example.com/article",
        }

        response = self.client.post(url, data, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        mock_task.assert_called_once()

        # Verify article was created
        article = Article.objects.get(source_url="https://example.com/article")
        self.assertEqual(article.feed, self.feed)

    def test_create_article_invalid_feed_token(self):
        """Test creating article with invalid feed token."""
        url = reverse("api:article-create")
        data = {
            "feed_token": "invalid-uuid",
            "title": "New Article",
            "text_content": "This is new content.",
        }

        response = self.client.post(url, data, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_article_unauthorized_feed(self):
        """Test creating article for another user's feed."""
        url = reverse("api:article-create")
        data = {
            "feed_token": str(self.other_feed.token),
            "title": "New Article",
            "text_content": "This is new content.",
        }

        response = self.client.post(url, data, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Invalid feed token", str(response.data))

    def test_create_article_validation_errors(self):
        """Test article creation validation."""
        url = reverse("api:article-create")

        # Test missing both URL and text
        data = {"feed_token": str(self.feed.token), "title": "New Article"}
        response = self.client.post(url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        # Test both URL and text provided
        data = {
            "feed_token": str(self.feed.token),
            "title": "New Article",
            "source_url": "https://example.com",
            "text_content": "Some text",
        }
        response = self.client.post(url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        # Test text without title
        data = {
            "feed_token": str(self.feed.token),
            "text_content": "Some text without title",
        }
        response = self.client.post(url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class APIStatusTests(APITestCase):
    """Test API status endpoint."""

    def setUp(self):
        """Set up test data with authentication."""
        super().setUp()
        self.token = Token.objects.create(user=self.user)
        self.client.credentials(HTTP_AUTHORIZATION="Token " + self.token.key)

    def test_api_status(self):
        """Test API status endpoint."""
        url = reverse("api:status")
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["user"], self.user.username)
        self.assertTrue(response.data["has_api_token"])
        self.assertEqual(response.data["feed_count"], 1)
        self.assertEqual(response.data["article_count"], 0)
        self.assertEqual(response.data["api_version"], "v1")
