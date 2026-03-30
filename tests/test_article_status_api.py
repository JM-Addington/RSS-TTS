"""Tests for the article status API."""

import json
import uuid

from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse

from text_to_audio.models import Article, Feed


class ArticleStatusAPITests(TestCase):
    """Test cases for the article status API endpoints."""

    def setUp(self):
        """Set up test data for each test."""
        self.client = Client()
        self.user = User.objects.create_user(username="testuser", password="pass")
        self.client.login(username="testuser", password="pass")
        self.feed = Feed.objects.create(user=self.user, name="Test Feed")
        self.article1 = Article.objects.create(
            feed=self.feed,
            title="A1",
            text_content="x",
            status=Article.PROCESSING,
            audio_uuid=uuid.uuid4(),
        )
        self.article2 = Article.objects.create(
            feed=self.feed,
            title="A2",
            text_content="x",
            status=Article.COMPLETED,
            audio_uuid=uuid.uuid4(),
        )

    def test_article_status_json(self):
        """Test that the API returns article statuses as JSON."""
        response = self.client.get(
            reverse("feed-article-status", kwargs={"feed_id": self.feed.pk})
        )
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertIn("articles", data)
        self.assertEqual(len(data["articles"]), 2)
        ids = {a["id"] for a in data["articles"]}
        self.assertIn(self.article1.pk, ids)
        self.assertIn(self.article2.pk, ids)
        statuses = {a["id"]: a["status"] for a in data["articles"]}
        self.assertEqual(statuses[self.article1.pk], self.article1.status)
        self.assertEqual(statuses[self.article2.pk], self.article2.status)

    def test_article_status_other_user(self):
        """Test that users can't access other users' feed article statuses."""
        other_user = User.objects.create_user(username="other", password="pass")
        other_feed = Feed.objects.create(user=other_user, name="Other")
        response = self.client.get(
            reverse("feed-article-status", kwargs={"feed_id": other_feed.pk})
        )
        self.assertEqual(response.status_code, 404)

    def test_empty_feed_returns_empty_articles(self):
        """Test that a feed with no articles returns an empty list. Closes #196."""
        empty_feed = Feed.objects.create(user=self.user, name="Empty Feed")
        response = self.client.get(
            reverse("feed-article-status", kwargs={"feed_id": empty_feed.pk})
        )
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertIn("articles", data)
        self.assertEqual(data["articles"], [])

    def test_unauthenticated_access_redirects(self):
        """Test that unauthenticated access redirects to login. Closes #196."""
        # AIDEV-NOTE: LoginRequiredMixin returns 302, not 401/403
        unauth_client = Client()
        response = unauth_client.get(
            reverse("feed-article-status", kwargs={"feed_id": self.feed.pk})
        )
        self.assertEqual(response.status_code, 302)

    def _create_articles(self, count):
        """Helper to bulk-create articles for pagination tests."""
        articles = [
            Article(
                feed=self.feed,
                title=f"Article {i}",
                text_content="x",
                status=Article.PROCESSING,
                audio_uuid=uuid.uuid4(),
            )
            for i in range(count)
        ]
        Article.objects.bulk_create(articles)

    def _get_status(self, **params):
        """Helper to GET the feed-article-status endpoint with query params."""
        url = reverse("feed-article-status", kwargs={"feed_id": self.feed.pk})
        return self.client.get(url, params)

    def test_pagination_default_limit(self):
        """Test that default page size is 100 and pagination metadata is present."""
        self._create_articles(110)  # + 2 from setUp = 112 total
        response = self._get_status()
        data = json.loads(response.content)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(data["articles"]), 100)
        pagination = data["pagination"]
        self.assertEqual(pagination["total_count"], 112)
        self.assertEqual(pagination["page"], 1)
        self.assertEqual(pagination["page_size"], 100)
        self.assertEqual(pagination["total_pages"], 2)
        self.assertTrue(pagination["has_next"])
        self.assertFalse(pagination["has_previous"])

    def test_pagination_page_param(self):
        """Test requesting page 2 returns remaining articles."""
        self._create_articles(110)  # 112 total
        response = self._get_status(page=2)
        data = json.loads(response.content)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(data["articles"]), 12)
        self.assertEqual(data["pagination"]["page"], 2)
        self.assertTrue(data["pagination"]["has_previous"])
        self.assertFalse(data["pagination"]["has_next"])

    def test_pagination_custom_page_size(self):
        """Test that page_size param controls number of results."""
        # 2 articles from setUp
        response = self._get_status(page_size=1)
        data = json.loads(response.content)
        self.assertEqual(len(data["articles"]), 1)
        self.assertEqual(data["pagination"]["page_size"], 1)
        self.assertEqual(data["pagination"]["total_pages"], 2)

    def test_pagination_max_page_size(self):
        """Test that page_size is capped at 100."""
        self._create_articles(110)  # 112 total
        response = self._get_status(page_size=500)
        data = json.loads(response.content)
        self.assertEqual(len(data["articles"]), 100)
        self.assertEqual(data["pagination"]["page_size"], 100)

    def test_pagination_invalid_page(self):
        """Test that an out-of-range page returns the last page."""
        # 2 articles from setUp, page_size=100 -> 1 page
        response = self._get_status(page=999)
        data = json.loads(response.content)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(data["articles"]), 2)
        self.assertEqual(data["pagination"]["page"], 1)

    def test_pagination_invalid_page_number_type(self):
        """Test that non-integer page/page_size params fall back to defaults."""
        response = self._get_status(page="abc", page_size="xyz")
        data = json.loads(response.content)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(data["pagination"]["page"], 1)
        self.assertEqual(data["pagination"]["page_size"], 100)

    def test_existing_behavior_preserved(self):
        """Test that small feeds return all articles with pagination metadata."""
        response = self._get_status()
        data = json.loads(response.content)
        self.assertEqual(len(data["articles"]), 2)
        self.assertEqual(data["pagination"]["total_count"], 2)
        self.assertEqual(data["pagination"]["total_pages"], 1)
        self.assertFalse(data["pagination"]["has_next"])
        self.assertFalse(data["pagination"]["has_previous"])
