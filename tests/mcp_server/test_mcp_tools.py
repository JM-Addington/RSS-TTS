"""Tests for the MCP CRUD tools (tools/list + tools/call).

Every domain entity (Feed, Article, FollowedFeed, UserVoicePreset) gets full
CRUD, scoped to the token's user. Business/validation failures come back as
tool results with isError=true (MCP spec SEP-1303), not protocol errors.
"""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings

from tests.mcp_server.helpers import call_tool, make_token, mcp_post, rpc, structured
from text_to_audio.models import Article, Feed, FollowedFeed, UserVoicePreset

User = get_user_model()
BASE = "http://testserver"

EXPECTED_TOOLS = {
    "create_feed",
    "list_feeds",
    "get_feed",
    "update_feed",
    "delete_feed",
    "create_article",
    "list_articles",
    "get_article",
    "update_article",
    "delete_article",
    "create_followed_feed",
    "list_followed_feeds",
    "get_followed_feed",
    "update_followed_feed",
    "delete_followed_feed",
    "create_voice_preset",
    "list_voice_presets",
    "get_voice_preset",
    "update_voice_preset",
    "delete_voice_preset",
}


@override_settings(MCP_ISSUER_URL=BASE)
class ToolTestBase(TestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(
            username="owner", email="owner@example.com", password="testpass123"
        )
        self.other_user = User.objects.create_user(
            username="intruder", email="other@example.com", password="testpass123"
        )
        self.token = make_token(self.user)
        self.other_token = make_token(self.other_user)

    def call(self, name, arguments=None, token=None):
        return call_tool(self.client, (token or self.token).token, name, arguments)

    def assert_tool_error(self, response, fragment=None):
        result = response.json()["result"]
        self.assertTrue(result.get("isError"), f"expected isError result: {result}")
        text = result["content"][0]["text"]
        if fragment:
            self.assertIn(fragment, text)
        return text


class ToolsListTests(ToolTestBase):
    def test_lists_all_crud_tools(self):
        response = mcp_post(self.client, rpc("tools/list"), token=self.token.token)
        tools = {t["name"]: t for t in response.json()["result"]["tools"]}
        self.assertEqual(set(tools), EXPECTED_TOOLS)

    def test_tool_schemas_and_annotations(self):
        response = mcp_post(self.client, rpc("tools/list"), token=self.token.token)
        tools = {t["name"]: t for t in response.json()["result"]["tools"]}
        for name, tool in tools.items():
            self.assertEqual(tool["inputSchema"]["type"], "object", name)
            self.assertTrue(tool["description"], name)
            annotations = tool["annotations"]
            # Closed-world: these tools only touch our own database.
            self.assertFalse(annotations["openWorldHint"], name)
            if name.startswith(("list_", "get_")):
                self.assertTrue(annotations["readOnlyHint"], name)
            else:
                self.assertFalse(annotations.get("readOnlyHint", False), name)
            if name.startswith("delete_"):
                self.assertTrue(annotations["destructiveHint"], name)
            elif name.startswith(("create_", "update_")):
                self.assertFalse(annotations["destructiveHint"], name)

    def test_unknown_tool_is_a_protocol_error(self):
        response = self.call("no_such_tool")
        self.assertEqual(response.json()["error"]["code"], -32602)


class FeedCrudTests(ToolTestBase):
    def test_create_feed(self):
        response = self.call("create_feed", {"name": "My Podcast"})
        data = structured(response)
        self.assertEqual(data["name"], "My Podcast")
        self.assertIn("token", data)
        self.assertIn("rss_url", data)
        feed = Feed.objects.get(pk=data["id"])
        self.assertEqual(feed.user, self.user)

    def test_create_feed_requires_name(self):
        response = self.call("create_feed", {"name": ""})
        self.assert_tool_error(response, "name")

    def test_list_feeds_only_returns_own(self):
        Feed.objects.create(user=self.user, name="Mine")
        Feed.objects.create(user=self.other_user, name="Theirs")
        data = structured(self.call("list_feeds"))
        self.assertEqual([f["name"] for f in data["feeds"]], ["Mine"])

    def test_get_feed(self):
        feed = Feed.objects.create(user=self.user, name="Mine")
        data = structured(self.call("get_feed", {"feed_id": feed.id}))
        self.assertEqual(data["id"], feed.id)
        self.assertEqual(data["article_count"], 0)

    def test_get_other_users_feed_is_not_found(self):
        feed = Feed.objects.create(user=self.other_user, name="Theirs")
        response = self.call("get_feed", {"feed_id": feed.id})
        self.assert_tool_error(response, "not found")

    def test_update_feed(self):
        feed = Feed.objects.create(user=self.user, name="Old")
        data = structured(
            self.call(
                "update_feed",
                {"feed_id": feed.id, "name": "New", "voice_mode": "auto"},
            )
        )
        self.assertEqual(data["name"], "New")
        feed.refresh_from_db()
        self.assertEqual(feed.name, "New")

    def test_update_feed_rejects_bad_voice_mode(self):
        feed = Feed.objects.create(user=self.user, name="F")
        response = self.call("update_feed", {"feed_id": feed.id, "voice_mode": "bogus"})
        self.assert_tool_error(response, "voice_mode")

    def test_delete_feed(self):
        feed = Feed.objects.create(user=self.user, name="Doomed")
        data = structured(self.call("delete_feed", {"feed_id": feed.id}))
        self.assertTrue(data["deleted"])
        self.assertFalse(Feed.objects.filter(pk=feed.id).exists())

    def test_delete_other_users_feed_is_not_found(self):
        feed = Feed.objects.create(user=self.other_user, name="Theirs")
        response = self.call("delete_feed", {"feed_id": feed.id})
        self.assert_tool_error(response, "not found")
        self.assertTrue(Feed.objects.filter(pk=feed.id).exists())


class ArticleCrudTests(ToolTestBase):
    def setUp(self):
        super().setUp()
        self.feed = Feed.objects.create(user=self.user, name="Feed")

    @patch("mcp_server.tools.process_article")
    def test_create_article_with_text(self, mock_process):
        response = self.call(
            "create_article",
            {
                "feed_id": self.feed.id,
                "title": "Hello",
                "text_content": "Some content to read aloud.",
            },
        )
        data = structured(response)
        article = Article.objects.get(pk=data["id"])
        self.assertEqual(article.feed, self.feed)
        self.assertEqual(article.status, Article.PROCESSING)
        mock_process.delay.assert_called_once_with(article.id)

    @patch("mcp_server.tools.process_article")
    def test_create_article_with_url(self, mock_process):
        response = self.call(
            "create_article",
            {"feed_id": self.feed.id, "source_url": "https://example.com/story"},
        )
        data = structured(response)
        self.assertEqual(data["source_url"], "https://example.com/story")
        mock_process.delay.assert_called_once()

    def test_create_article_requires_content_or_url(self):
        response = self.call("create_article", {"feed_id": self.feed.id})
        self.assert_tool_error(response)

    def test_create_article_text_without_title_is_rejected(self):
        response = self.call(
            "create_article",
            {"feed_id": self.feed.id, "text_content": "content"},
        )
        self.assert_tool_error(response, "title")

    def test_create_article_rejects_ssrf_url(self):
        response = self.call(
            "create_article",
            {"feed_id": self.feed.id, "source_url": "http://169.254.169.254/meta"},
        )
        self.assert_tool_error(response)

    def test_create_article_in_other_users_feed_is_not_found(self):
        other_feed = Feed.objects.create(user=self.other_user, name="Theirs")
        response = self.call(
            "create_article",
            {"feed_id": other_feed.id, "title": "X", "text_content": "Y"},
        )
        self.assert_tool_error(response, "not found")

    def test_list_articles_filters_by_feed_and_status(self):
        a1 = Article.objects.create(
            feed=self.feed, title="One", text_content="x", status=Article.COMPLETED
        )
        Article.objects.create(
            feed=self.feed, title="Two", text_content="x", status=Article.PROCESSING
        )
        other_feed = Feed.objects.create(user=self.other_user, name="Theirs")
        Article.objects.create(feed=other_feed, title="NotMine", text_content="x")

        data = structured(self.call("list_articles", {}))
        self.assertEqual(len(data["articles"]), 2)

        data = structured(
            self.call("list_articles", {"feed_id": self.feed.id, "status": "COMPLETED"})
        )
        self.assertEqual([a["id"] for a in data["articles"]], [a1.id])

    def test_get_article_includes_text_content(self):
        article = Article.objects.create(
            feed=self.feed, title="One", text_content="full body text"
        )
        data = structured(self.call("get_article", {"article_id": article.id}))
        self.assertEqual(data["text_content"], "full body text")

    def test_update_article(self):
        article = Article.objects.create(feed=self.feed, title="Old", text_content="x")
        data = structured(
            self.call(
                "update_article", {"article_id": article.id, "title": "New title"}
            )
        )
        self.assertEqual(data["title"], "New title")
        article.refresh_from_db()
        self.assertEqual(article.title, "New title")

    def test_delete_article(self):
        article = Article.objects.create(feed=self.feed, title="X", text_content="y")
        data = structured(self.call("delete_article", {"article_id": article.id}))
        self.assertTrue(data["deleted"])
        self.assertFalse(Article.objects.filter(pk=article.id).exists())

    def test_article_ownership_is_enforced(self):
        other_feed = Feed.objects.create(user=self.other_user, name="Theirs")
        article = Article.objects.create(
            feed=other_feed, title="Secret", text_content="z"
        )
        for tool, args in [
            ("get_article", {"article_id": article.id}),
            ("update_article", {"article_id": article.id, "title": "Hacked"}),
            ("delete_article", {"article_id": article.id}),
        ]:
            response = self.call(tool, args)
            self.assert_tool_error(response, "not found")


class FollowedFeedCrudTests(ToolTestBase):
    def setUp(self):
        super().setUp()
        self.feed = Feed.objects.create(user=self.user, name="Destination")

    def test_create_followed_feed(self):
        response = self.call(
            "create_followed_feed",
            {
                "url": "https://example.com/rss.xml",
                "destination_feed_id": self.feed.id,
            },
        )
        data = structured(response)
        followed = FollowedFeed.objects.get(pk=data["id"])
        self.assertEqual(followed.user, self.user)
        self.assertTrue(followed.fetch_full_text)
        self.assertTrue(followed.is_active)

    def test_create_followed_feed_requires_own_destination(self):
        other_feed = Feed.objects.create(user=self.other_user, name="Theirs")
        response = self.call(
            "create_followed_feed",
            {"url": "https://example.com/rss", "destination_feed_id": other_feed.id},
        )
        self.assert_tool_error(response, "not found")

    def test_create_duplicate_followed_feed_is_rejected(self):
        FollowedFeed.objects.create(
            user=self.user, url="https://example.com/rss", destination_feed=self.feed
        )
        response = self.call(
            "create_followed_feed",
            {"url": "https://example.com/rss", "destination_feed_id": self.feed.id},
        )
        self.assert_tool_error(response)

    def test_list_get_update_delete_followed_feed(self):
        followed = FollowedFeed.objects.create(
            user=self.user, url="https://example.com/rss", destination_feed=self.feed
        )
        FollowedFeed.objects.create(
            user=self.other_user,
            url="https://example.com/rss",
            destination_feed=Feed.objects.create(user=self.other_user, name="T"),
        )

        data = structured(self.call("list_followed_feeds"))
        self.assertEqual([f["id"] for f in data["followed_feeds"]], [followed.id])

        data = structured(
            self.call("get_followed_feed", {"followed_feed_id": followed.id})
        )
        self.assertEqual(data["url"], "https://example.com/rss")

        data = structured(
            self.call(
                "update_followed_feed",
                {"followed_feed_id": followed.id, "is_active": False},
            )
        )
        self.assertFalse(data["is_active"])
        followed.refresh_from_db()
        self.assertFalse(followed.is_active)

        data = structured(
            self.call("delete_followed_feed", {"followed_feed_id": followed.id})
        )
        self.assertTrue(data["deleted"])
        self.assertFalse(FollowedFeed.objects.filter(pk=followed.id).exists())


class VoicePresetCrudTests(ToolTestBase):
    def test_create_voice_preset(self):
        response = self.call(
            "create_voice_preset",
            {"name": "Calm narrator", "voice_id": "nova", "speed": 1.1},
        )
        data = structured(response)
        preset = UserVoicePreset.objects.get(pk=data["id"])
        self.assertEqual(preset.user, self.user)
        self.assertEqual(preset.voice_id, "nova")
        self.assertAlmostEqual(preset.speed, 1.1)

    def test_create_voice_preset_rejects_bad_voice(self):
        response = self.call(
            "create_voice_preset", {"name": "Bad", "voice_id": "not-a-voice"}
        )
        self.assert_tool_error(response, "voice_id")

    def test_create_duplicate_name_is_rejected(self):
        UserVoicePreset.objects.create(
            user=self.user, name="Dup", voice_id="nova", speed=1.0
        )
        response = self.call(
            "create_voice_preset", {"name": "Dup", "voice_id": "alloy"}
        )
        self.assert_tool_error(response)

    def test_list_get_update_delete_voice_preset(self):
        preset = UserVoicePreset.objects.create(
            user=self.user, name="Mine", voice_id="nova", speed=1.0
        )
        UserVoicePreset.objects.create(
            user=self.other_user, name="Theirs", voice_id="alloy", speed=1.0
        )

        data = structured(self.call("list_voice_presets"))
        self.assertEqual([p["id"] for p in data["voice_presets"]], [preset.id])

        data = structured(self.call("get_voice_preset", {"preset_id": preset.id}))
        self.assertEqual(data["name"], "Mine")

        data = structured(
            self.call("update_voice_preset", {"preset_id": preset.id, "speed": 1.5})
        )
        self.assertAlmostEqual(data["speed"], 1.5)

        data = structured(self.call("delete_voice_preset", {"preset_id": preset.id}))
        self.assertTrue(data["deleted"])
        self.assertFalse(UserVoicePreset.objects.filter(pk=preset.id).exists())


class MalformedInputRobustnessTests(ToolTestBase):
    """Non-string / unhashable JSON values must yield isError tool results,
    never TypeError/AttributeError 500s (PR #240 review)."""

    def setUp(self):
        super().setUp()
        self.feed = Feed.objects.create(user=self.user, name="Feed")

    def test_create_feed_rejects_non_string_voice_mode(self):
        response = self.call(
            "create_feed", {"name": "F", "voice_mode": {"nested": "dict"}}
        )
        self.assert_tool_error(response, "voice_mode")

    def test_create_feed_rejects_non_string_tts_provider(self):
        response = self.call("create_feed", {"name": "F", "tts_provider": ["openai"]})
        self.assert_tool_error(response, "tts_provider")

    def test_create_article_rejects_non_string_voice(self):
        response = self.call(
            "create_article",
            {"feed_id": self.feed.id, "title": "T", "text_content": "x", "voice": {}},
        )
        self.assert_tool_error(response, "voice")

    def test_create_article_rejects_non_string_source_url(self):
        response = self.call(
            "create_article",
            {"feed_id": self.feed.id, "source_url": ["https://example.com"]},
        )
        self.assert_tool_error(response, "source_url")

    def test_create_article_model_validation_is_tool_error(self):
        # Valid public URL but longer than the model's 2000-char limit:
        # full_clean must surface as an isError result, not a 500.
        long_url = "https://example.com/" + "a" * 2100
        response = self.call(
            "create_article", {"feed_id": self.feed.id, "source_url": long_url}
        )
        self.assert_tool_error(response)

    def test_list_articles_rejects_non_string_status(self):
        response = self.call("list_articles", {"status": ["COMPLETED"]})
        self.assert_tool_error(response, "status")

    def test_create_followed_feed_rejects_non_string_url(self):
        response = self.call(
            "create_followed_feed",
            {"url": ["https://example.com/rss"], "destination_feed_id": self.feed.id},
        )
        self.assert_tool_error(response, "url")

    def test_update_followed_feed_rejects_non_string_url(self):
        followed = FollowedFeed.objects.create(
            user=self.user, url="https://example.com/rss", destination_feed=self.feed
        )
        response = self.call(
            "update_followed_feed",
            {"followed_feed_id": followed.id, "url": ["https://evil.example"]},
        )
        self.assert_tool_error(response, "url")
        followed.refresh_from_db()
        self.assertEqual(followed.url, "https://example.com/rss")

    def test_create_voice_preset_rejects_non_string_voice_id(self):
        response = self.call(
            "create_voice_preset", {"name": "P", "voice_id": {"voice": "nova"}}
        )
        self.assert_tool_error(response, "voice_id")

    def test_update_voice_preset_rejects_non_string_voice_id(self):
        preset = UserVoicePreset.objects.create(
            user=self.user, name="P", voice_id="nova", speed=1.0
        )
        response = self.call(
            "update_voice_preset", {"preset_id": preset.id, "voice_id": ["alloy"]}
        )
        self.assert_tool_error(response, "voice_id")

    def test_unexpected_handler_exception_returns_internal_error(self):
        """Safety net: an unexpected exception inside a tool handler must map
        to JSON-RPC -32603, never a Django 500."""
        from mcp_server import registry

        tool = registry.get_tool("list_feeds")
        original_handler = tool.handler
        tool.handler = lambda user, args: (_ for _ in ()).throw(RuntimeError("boom"))
        try:
            response = self.call("list_feeds")
        finally:
            tool.handler = original_handler
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["error"]["code"], -32603)
        self.assertNotIn("boom", body["error"]["message"])  # no detail leakage


class WordCapAndPresetAssignmentTests(ToolTestBase):
    """Codex review: enforce the 40k-word article cap (parity with the REST
    API) and make voice presets assignable to feeds and articles."""

    def setUp(self):
        super().setUp()
        self.feed = Feed.objects.create(user=self.user, name="Feed")
        self.preset = UserVoicePreset.objects.create(
            user=self.user, name="Mine", voice_id="nova", speed=1.0
        )

    @patch("mcp_server.tools.process_article")
    def test_create_article_enforces_word_cap(self, mock_process):
        response = self.call(
            "create_article",
            {
                "feed_id": self.feed.id,
                "title": "Long",
                "text_content": "word " * 40001,
            },
        )
        self.assert_tool_error(response, "words")
        mock_process.delay.assert_not_called()
        self.assertEqual(Article.objects.count(), 0)

    def test_update_article_enforces_word_cap(self):
        article = Article.objects.create(feed=self.feed, title="T", text_content="x")
        response = self.call(
            "update_article",
            {"article_id": article.id, "text_content": "word " * 40001},
        )
        self.assert_tool_error(response, "words")
        article.refresh_from_db()
        self.assertEqual(article.text_content, "x")

    def test_feed_default_voice_preset_set_and_clear(self):
        data = structured(
            self.call(
                "create_feed",
                {"name": "WithPreset", "default_voice_preset_id": self.preset.id},
            )
        )
        self.assertEqual(data["default_voice_preset_id"], self.preset.id)
        data = structured(
            self.call(
                "update_feed",
                {"feed_id": data["id"], "default_voice_preset_id": None},
            )
        )
        self.assertIsNone(data["default_voice_preset_id"])

    def test_feed_preset_must_be_owned(self):
        other_preset = UserVoicePreset.objects.create(
            user=self.other_user, name="Theirs", voice_id="alloy", speed=1.0
        )
        response = self.call(
            "create_feed",
            {"name": "F", "default_voice_preset_id": other_preset.id},
        )
        self.assert_tool_error(response, "not found")

    @patch("mcp_server.tools.process_article")
    def test_create_article_with_voice_preset(self, mock_process):
        data = structured(
            self.call(
                "create_article",
                {
                    "feed_id": self.feed.id,
                    "title": "T",
                    "text_content": "hello world",
                    "voice_preset_id": self.preset.id,
                },
            )
        )
        article = Article.objects.get(pk=data["id"])
        self.assertEqual(article.voice_preset, self.preset)
        self.assertEqual(data["voice_preset_id"], self.preset.id)
        # Preset voice/speed must be copied onto the article, or
        # VoiceConfigurationService will override the preset at processing
        # time (it only honors presets whose voice fields already match).
        self.assertEqual(article.voice, self.preset.voice_id)
        self.assertEqual(article.speed, self.preset.speed)

    @patch("mcp_server.tools.process_article")
    def test_create_article_preset_speed_can_be_overridden(self, mock_process):
        data = structured(
            self.call(
                "create_article",
                {
                    "feed_id": self.feed.id,
                    "title": "T",
                    "text_content": "hello",
                    "voice_preset_id": self.preset.id,
                    "speed": 1.7,
                },
            )
        )
        article = Article.objects.get(pk=data["id"])
        self.assertEqual(article.voice, self.preset.voice_id)
        self.assertAlmostEqual(article.speed, 1.7)

    @patch("mcp_server.tools.process_article")
    def test_create_article_rejects_voice_and_preset_together(self, mock_process):
        response = self.call(
            "create_article",
            {
                "feed_id": self.feed.id,
                "title": "T",
                "text_content": "hello",
                "voice": "alloy",
                "voice_preset_id": self.preset.id,
            },
        )
        self.assert_tool_error(response)
        mock_process.delay.assert_not_called()

    @patch("mcp_server.tools.process_article")
    def test_create_article_rejects_foreign_voice_preset(self, mock_process):
        other_preset = UserVoicePreset.objects.create(
            user=self.other_user, name="Theirs", voice_id="alloy", speed=1.0
        )
        response = self.call(
            "create_article",
            {
                "feed_id": self.feed.id,
                "title": "T",
                "text_content": "hello",
                "voice_preset_id": other_preset.id,
            },
        )
        self.assert_tool_error(response, "not found")
        mock_process.delay.assert_not_called()


class PresetModeCouplingTests(ToolTestBase):
    """Codex review: a default preset must actually take effect — processing
    only honors feed.default_voice_preset in single_custom voice mode."""

    def setUp(self):
        super().setUp()
        self.preset = UserVoicePreset.objects.create(
            user=self.user, name="Narrator", voice_id="nova", speed=1.0
        )

    def test_create_feed_with_preset_defaults_to_single_custom(self):
        data = structured(
            self.call(
                "create_feed",
                {"name": "F", "default_voice_preset_id": self.preset.id},
            )
        )
        self.assertEqual(data["voice_mode"], "single_custom")
        self.assertEqual(data["default_voice_preset_id"], self.preset.id)

    def test_create_feed_preset_with_conflicting_mode_is_rejected(self):
        response = self.call(
            "create_feed",
            {
                "name": "F",
                "default_voice_preset_id": self.preset.id,
                "voice_mode": "auto",
            },
        )
        self.assert_tool_error(response, "single_custom")

    def test_update_feed_preset_switches_mode_and_clearing_reverts(self):
        feed = Feed.objects.create(user=self.user, name="F")
        data = structured(
            self.call(
                "update_feed",
                {"feed_id": feed.id, "default_voice_preset_id": self.preset.id},
            )
        )
        self.assertEqual(data["voice_mode"], "single_custom")
        data = structured(
            self.call(
                "update_feed",
                {"feed_id": feed.id, "default_voice_preset_id": None},
            )
        )
        self.assertIsNone(data["default_voice_preset_id"])
        self.assertEqual(data["voice_mode"], "auto")


class AudioFileCleanupTests(ToolTestBase):
    """Codex review: deleting articles/feeds must remove the canonical MP3s,
    matching the web ArticleDeleteView behavior."""

    def setUp(self):
        super().setUp()
        self.feed = Feed.objects.create(user=self.user, name="Feed")

    def _make_article_with_audio(self, media_root, title="A"):
        import os
        import uuid as uuid_module

        article = Article.objects.create(
            feed=self.feed,
            title=title,
            text_content="x",
            status=Article.COMPLETED,
            audio_uuid=uuid_module.uuid4(),
        )
        audio_dir = os.path.join(media_root, "articles")
        os.makedirs(audio_dir, exist_ok=True)
        path = os.path.join(audio_dir, f"{article.audio_uuid}.mp3")
        with open(path, "wb") as f:
            f.write(b"fake mp3 bytes")
        return article, path

    def test_delete_article_removes_audio_file(self):
        import os
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            with self.settings(MEDIA_ROOT=tmp):
                article, path = self._make_article_with_audio(tmp)
                data = structured(
                    self.call("delete_article", {"article_id": article.id})
                )
                self.assertTrue(data["deleted"])
                self.assertFalse(os.path.exists(path))

    def test_delete_feed_removes_article_audio_files(self):
        import os
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            with self.settings(MEDIA_ROOT=tmp):
                _, path_a = self._make_article_with_audio(tmp, "A")
                _, path_b = self._make_article_with_audio(tmp, "B")
                data = structured(self.call("delete_feed", {"feed_id": self.feed.id}))
                self.assertTrue(data["deleted"])
                self.assertFalse(os.path.exists(path_a))
                self.assertFalse(os.path.exists(path_b))


class FollowedFeedDuplicateUpdateTests(ToolTestBase):
    """Codex review: updating a followed feed into an existing (url,
    destination) pair must be a validation error, not an IntegrityError."""

    def test_update_into_duplicate_pair_is_tool_error(self):
        feed = Feed.objects.create(user=self.user, name="Dest")
        FollowedFeed.objects.create(
            user=self.user, url="https://example.com/a.xml", destination_feed=feed
        )
        other = FollowedFeed.objects.create(
            user=self.user, url="https://example.com/b.xml", destination_feed=feed
        )
        response = self.call(
            "update_followed_feed",
            {"followed_feed_id": other.id, "url": "https://example.com/a.xml"},
        )
        self.assert_tool_error(response, "Already following")
        other.refresh_from_db()
        self.assertEqual(other.url, "https://example.com/b.xml")


class ExclusiveInputAndTaskRevocationTests(ToolTestBase):
    """Codex review round 5: reject url+text together (REST parity) and
    revoke in-flight narration tasks when deleting articles/feeds."""

    def setUp(self):
        super().setUp()
        self.feed = Feed.objects.create(user=self.user, name="Feed")

    @patch("mcp_server.tools.process_article")
    def test_create_article_rejects_url_and_text_together(self, mock_process):
        response = self.call(
            "create_article",
            {
                "feed_id": self.feed.id,
                "title": "T",
                "text_content": "some text",
                "source_url": "https://example.com/story",
            },
        )
        self.assert_tool_error(response, "not both")
        mock_process.delay.assert_not_called()

    @patch("mcp_server.tools.celery_app")
    def test_delete_article_revokes_processing_task(self, mock_celery):
        article = Article.objects.create(
            feed=self.feed,
            title="T",
            text_content="x",
            status=Article.PROCESSING,
            celery_task_id="task-abc",
        )
        structured(self.call("delete_article", {"article_id": article.id}))
        mock_celery.control.revoke.assert_called_once_with("task-abc", terminate=True)

    @patch("mcp_server.tools.celery_app")
    def test_delete_completed_article_does_not_revoke(self, mock_celery):
        article = Article.objects.create(
            feed=self.feed,
            title="T",
            text_content="x",
            status=Article.COMPLETED,
            celery_task_id="task-abc",
        )
        structured(self.call("delete_article", {"article_id": article.id}))
        mock_celery.control.revoke.assert_not_called()

    @patch("mcp_server.tools.celery_app")
    def test_delete_feed_revokes_processing_tasks(self, mock_celery):
        Article.objects.create(
            feed=self.feed,
            title="A",
            text_content="x",
            status=Article.PROCESSING,
            celery_task_id="task-1",
        )
        Article.objects.create(
            feed=self.feed,
            title="B",
            text_content="x",
            status=Article.COMPLETED,
            celery_task_id="task-2",
        )
        structured(self.call("delete_feed", {"feed_id": self.feed.id}))
        mock_celery.control.revoke.assert_called_once_with("task-1", terminate=True)

    @patch("mcp_server.tools.celery_app")
    def test_revoke_failure_does_not_block_deletion(self, mock_celery):
        mock_celery.control.revoke.side_effect = RuntimeError("broker down")
        article = Article.objects.create(
            feed=self.feed,
            title="T",
            text_content="x",
            status=Article.PROCESSING,
            celery_task_id="task-abc",
        )
        data = structured(self.call("delete_article", {"article_id": article.id}))
        self.assertTrue(data["deleted"])
        self.assertFalse(Article.objects.filter(pk=article.id).exists())
