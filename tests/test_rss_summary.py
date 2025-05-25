from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from text_to_audio.models import Article, Feed


class RssSummaryTests(TestCase):
    """Tests for summary inclusion in RSS feed."""

    def setUp(self):
        self.client = Client()
        self.user = get_user_model().objects.create_user(  # type: ignore[attr-defined]
            username="rssuser", password="pass123"
        )
        self.feed = Feed.objects.create(user=self.user, name="Test Feed")
        self.article = Article.objects.create(
            feed=self.feed,
            title="Summary Article",
            text_content="body",
            summary="A short summary.",
            audio_file_path="dummy.mp3",
            audio_uuid="123e4567-e89b-12d3-a456-426614174000",
            status=Article.COMPLETED,
        )

    def test_summary_in_feed(self):
        response = self.client.get(reverse("feed", args=[self.feed.token]))
        self.assertEqual(response.status_code, 200)
        self.assertIn("A short summary.", response.content.decode())
