"""Tests for article summary generation and inclusion in RSS feeds."""

import uuid
from unittest.mock import MagicMock, patch

from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse

from text_to_audio.models import Article, Feed
from text_to_audio.tasks import process_article


class ArticleSummaryTests(TestCase):
    """Tests for article summary generation and RSS feed inclusion."""

    def setUp(self):
        """Set up test environment."""
        self.client = Client()
        self.user = User.objects.create_user(
            username="summarytest", password="testpass"
        )
        self.feed = Feed.objects.create(user=self.user, name="Summary Test Feed")
        self.article = Article.objects.create(
            feed=self.feed,
            title="Summary Test Article",
            text_content="This is test content for generating a summary.",
            status=Article.PROCESSING,
        )

    @patch("text_to_audio.tasks.openai.OpenAI")
    def test_summary_generation_during_processing(self, mock_openai):
        """Test that a summary is generated during article processing."""
        # Mock OpenAI client for both TTS and chat completions
        mock_openai_instance = mock_openai.return_value

        # Mock chat completions for summary generation
        mock_chat_completions = mock_openai_instance.chat.completions
        mock_chat_completions.create.return_value = MagicMock(
            choices=[
                MagicMock(
                    message=MagicMock(content="This is a test summary of the article.")
                )
            ]
        )

        # Mock speech creation for audio generation
        mock_speech_create = mock_openai_instance.audio.speech.create
        mock_speech_response = MagicMock()
        mock_speech_response.stream_to_file.side_effect = lambda path: open(
            path, "w"
        ).write("mock audio")
        mock_speech_create.return_value = mock_speech_response

        # Additional mocks for audio processing
        with patch("text_to_audio.tasks.AudioSegment.from_mp3") as mock_from_mp3, patch(
            "text_to_audio.tasks.AudioSegment.empty"
        ) as mock_empty:

            # Configure audio segment mocks
            mock_audio_segment = MagicMock()
            mock_audio_segment.set_frame_rate.return_value = mock_audio_segment
            mock_audio_segment.export.side_effect = lambda path, **kwargs: open(
                path, "w"
            ).write("mock audio")
            mock_from_mp3.return_value = mock_audio_segment
            mock_empty.return_value = MagicMock()

            # Process the article
            process_article(self.article.pk)

        # Check if summary was generated
        self.article.refresh_from_db()
        self.assertEqual(self.article.status, Article.COMPLETED)
        self.assertIsNotNone(self.article.summary)
        self.assertEqual(self.article.summary, "This is a test summary of the article.")

        # Verify the OpenAI chat completions call
        mock_chat_completions.create.assert_called_once()
        call_args = mock_chat_completions.create.call_args[1]
        self.assertEqual(call_args["max_tokens"], 150)
        self.assertAlmostEqual(call_args["temperature"], 0.3)

        # Check the messages format
        messages = call_args["messages"]
        self.assertEqual(len(messages), 2)
        self.assertEqual(messages[0]["role"], "system")
        self.assertEqual(messages[1]["role"], "user")
        self.assertIn(self.article.title, messages[1]["content"])

    def test_summary_included_in_rss_feed(self):
        """Test that article summary is included in RSS feed description."""
        # Set up a completed article with a summary
        article = Article.objects.create(
            feed=self.feed,
            title="RSS Summary Test",
            text_content="This is test content.",
            summary="This is a test summary for the RSS feed.",
            status=Article.COMPLETED,
            audio_uuid=uuid.uuid4(),
            audio_file_path="test/path/audio.mp3",
        )

        # Get the RSS feed
        response = self.client.get(reverse("feed", kwargs={"token": self.feed.token}))

        # Check response
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/rss+xml; charset=utf-8")

        # Check for the summary in the response content
        self.assertIn(article.summary, response.content.decode())

        # Check for both the article title and summary
        content = response.content.decode()
        self.assertIn(article.title, content)
        self.assertIn(article.summary, content)
