from django.test import Client, TestCase
from django.contrib.auth import get_user_model
from django.urls import reverse
import uuid

from text_to_audio.models import Feed, Article


class AudioPlayerDisplayTests(TestCase):
    """Tests for in-app audio player display."""

    def setUp(self):
        self.client = Client()
        self.user = get_user_model().objects.create_user(
            username="audiotester", password="pass123"
        )
        self.feed = Feed.objects.create(user=self.user, name="My Feed")
        self.article = Article.objects.create(
            feed=self.feed,
            title="Completed Article",
            text_content="Sample text",
            audio_uuid=uuid.uuid4(),
            status=Article.COMPLETED,
        )
        self.client.login(username="audiotester", password="pass123")

    def test_completed_article_shows_audio_player(self):
        """Completed articles should include an <audio> player."""
        response = self.client.get(
            reverse("feed-articles", kwargs={"feed_id": self.feed.pk})
        )
        audio_url = reverse("article-media", kwargs={"audio_uuid": self.article.audio_uuid})
        self.assertContains(response, "<audio", html=False)
        self.assertContains(response, audio_url)

