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
