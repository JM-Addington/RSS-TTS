# flake8: noqa
# mypy: ignore-errors
"""Tests for N+1 query optimization in RegenerateArticleView.

AIDEV-NOTE: Verifies that RegenerateArticleView uses select_related
for voice_preset to avoid extra queries when regenerating an article.
"""

import uuid
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import connection, reset_queries
from django.test import Client, TestCase, override_settings

from text_to_audio.models import Article, Feed, UserVoicePreset

User = get_user_model()


class RegenerateArticleQueryCountTests(TestCase):
    """Tests that RegenerateArticleView doesn't issue N+1 queries for voice_preset."""

    def setUp(self):
        self.user = User.objects.create_user(username="querytest", password="testpass")
        self.client = Client()
        self.client.login(username="querytest", password="testpass")
        self.feed = Feed.objects.create(user=self.user, name="Test Feed")
        self.preset = UserVoicePreset.objects.create(
            user=self.user,
            name="Test Preset",
            voice_id="alloy",
            speed=1.0,
        )
        self.article = Article.objects.create(
            feed=self.feed,
            title="Test Article",
            text_content="Some content",
            voice_preset=self.preset,
            audio_uuid=uuid.uuid4(),
        )

    @override_settings(DEBUG=True)
    @patch("text_to_audio.views.process_article.delay")
    def test_no_extra_query_for_voice_preset(self, mock_delay):
        """Accessing original_article.voice_preset should not cause an extra query."""
        mock_delay.return_value.id = "fake-task-id"

        reset_queries()
        response = self.client.post(f"/articles/{self.article.id}/regenerate/")
        queries = list(connection.queries)

        # Should redirect (302) on success
        self.assertIn(response.status_code, [200, 302])

        # Check that no standalone query fetches a single voice_preset by ID
        # (N+1 pattern). A JOINed article query including voice_preset is fine.
        voice_preset_n_plus_1 = [
            q for q in queries
            if q["sql"].lower().lstrip().startswith("select")
            and "uservoicepreset" in q["sql"].lower()
            and "text_to_audio_article" not in q["sql"].lower()
        ]
        self.assertEqual(
            len(voice_preset_n_plus_1),
            0,
            f"Found {len(voice_preset_n_plus_1)} N+1 voice_preset query(ies): "
            f"{voice_preset_n_plus_1}. Should be JOINed via select_related.",
        )
