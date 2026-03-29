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
