"""Tests for audio player display in article list."""

import uuid

from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse

from text_to_audio.models import Article, Feed


class AudioPlayerDisplayTests(TestCase):
    """Tests for audio player in article list view."""

    def setUp(self):
        """Set up the test environment.

        Create a test user, feed, and completed article with audio.
        """
        self.client = Client()
        self.user = User.objects.create_user(
            username="audiotest", password="audiopassword"
        )
        self.client.login(username="audiotest", password="audiopassword")

        # Create a feed
        self.feed = Feed.objects.create(user=self.user, name="Audio Test Feed")

        # Create a completed article with audio UUID
        self.article = Article.objects.create(
            feed=self.feed,
            title="Audio Player Test",
            text_content="This is test content for audio player.",
            status=Article.COMPLETED,
            audio_uuid=uuid.uuid4(),
            audio_file_path=f"articles/{uuid.uuid4()}.mp3",  # Dummy path
        )

    def test_audio_player_displays_for_completed_articles(self):
        """Test that audio player is displayed for completed articles."""
        # Get the article list page
        response = self.client.get(
            reverse("feed-articles", kwargs={"feed_id": self.feed.pk})
        )

        # Check for success
        self.assertEqual(response.status_code, 200)

        # Check for audio player element
        self.assertContains(response, "<audio controls")
        audio_url = reverse(
            "article-media", kwargs={"audio_uuid": self.article.audio_uuid}
        )
        self.assertContains(response, f'src="{audio_url}"')
        self.assertContains(response, 'type="audio/mpeg"')

        # Check that the audio source URL is correct
        expected_url = reverse(
            "article-media", kwargs={"audio_uuid": self.article.audio_uuid}
        )
        self.assertContains(response, f'src="{expected_url}"')
