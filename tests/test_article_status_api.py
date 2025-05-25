from django.test import Client, TestCase
from django.urls import reverse
from django.contrib.auth.models import User

from text_to_audio.models import Feed, Article
import uuid
import json


class ArticleStatusAPITests(TestCase):
    def setUp(self):
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
        response = self.client.get(
            reverse("feed-article-status", kwargs={"feed_id": self.feed.pk})
        )
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertIn("articles", data)
        self.assertEqual(len(data["articles"]), 2)
        ids = {a["id"] for a in data["articles"]}
        self.assertIn(self.article1.id, ids)
        self.assertIn(self.article2.id, ids)
        statuses = {a["id"]: a["status"] for a in data["articles"]}
        self.assertEqual(statuses[self.article1.id], self.article1.status)
        self.assertEqual(statuses[self.article2.id], self.article2.status)

    def test_article_status_other_user(self):
        other_user = User.objects.create_user(username="other", password="pass")
        other_feed = Feed.objects.create(user=other_user, name="Other")
        response = self.client.get(
            reverse("feed-article-status", kwargs={"feed_id": other_feed.pk})
        )
        self.assertEqual(response.status_code, 404)

