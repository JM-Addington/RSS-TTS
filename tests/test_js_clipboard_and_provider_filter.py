"""Tests for extracted clipboard_utils.js and provider_filter.js static files."""

# mypy: disable-error-code="attr-defined"

import os
import uuid

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import Client, TestCase

from text_to_audio.models import Article, Feed


STATIC_JS_DIR = os.path.join(
    settings.BASE_DIR,
    "text_to_audio",
    "static",
    "text_to_audio",
    "js",
)


class TestClipboardUtilsJSExists(TestCase):
    """Verify clipboard_utils.js exists and has expected content."""

    def test_file_exists(self):
        path = os.path.join(STATIC_JS_DIR, "clipboard_utils.js")
        self.assertTrue(os.path.isfile(path), f"Missing {path}")

    def test_contains_copy_function(self):
        path = os.path.join(STATIC_JS_DIR, "clipboard_utils.js")
        with open(path) as f:
            content = f.read()
        self.assertIn("clipboard", content.lower())
        self.assertIn("data-clipboard-target", content)

    def test_has_execcommand_fallback(self):
        path = os.path.join(STATIC_JS_DIR, "clipboard_utils.js")
        with open(path) as f:
            content = f.read()
        self.assertIn("execCommand", content)


class TestProviderFilterJSExists(TestCase):
    """Verify provider_filter.js exists and has expected content."""

    def test_file_exists(self):
        path = os.path.join(STATIC_JS_DIR, "provider_filter.js")
        self.assertTrue(os.path.isfile(path), f"Missing {path}")

    def test_contains_filter_logic(self):
        path = os.path.join(STATIC_JS_DIR, "provider_filter.js")
        with open(path) as f:
            content = f.read()
        self.assertIn("data-provider-select", content)

    def test_handles_voice_and_preset(self):
        path = os.path.join(STATIC_JS_DIR, "provider_filter.js")
        with open(path) as f:
            content = f.read()
        self.assertIn("data-voice-select", content)
        self.assertIn("data-preset-select", content)


class TestFeedListClipboardExtraction(TestCase):
    """Verify feed_list.html uses clipboard_utils.js instead of inline JS."""

    def setUp(self):
        self.client = Client()
        self.user = get_user_model().objects.create_user(
            username="cliptest", password="pass123"
        )
        self.feed = Feed.objects.create(user=self.user, name="Clip Test Feed")
        self.client.login(username="cliptest", password="pass123")

    def test_includes_clipboard_utils_js(self):
        response = self.client.get("/feeds/")
        self.assertContains(response, "clipboard_utils.js")

    def test_no_inline_copyToClipboard_function(self):
        response = self.client.get("/feeds/")
        content = response.content.decode()
        self.assertNotIn("function copyToClipboard", content)

    def test_copy_buttons_have_data_attributes(self):
        response = self.client.get("/feeds/")
        content = response.content.decode()
        self.assertIn("data-clipboard-target", content)


class TestArticleListClipboardExtraction(TestCase):
    """Verify article_list.html uses clipboard_utils.js."""

    def setUp(self):
        self.client = Client()
        self.user = get_user_model().objects.create_user(
            username="artclip", password="pass123"
        )
        self.feed = Feed.objects.create(user=self.user, name="Art Clip Feed")
        self.client.login(username="artclip", password="pass123")

    def test_includes_clipboard_utils_js(self):
        response = self.client.get(f"/feeds/{self.feed.pk}/")
        self.assertContains(response, "clipboard_utils.js")

    def test_copy_buttons_have_data_attributes(self):
        response = self.client.get(f"/feeds/{self.feed.pk}/")
        content = response.content.decode()
        self.assertIn("data-clipboard-target", content)


class TestArticleListJSNoCopyFunctions(TestCase):
    """Verify article_list.js no longer contains duplicated copy functions."""

    def test_no_copyFeedUrl_function(self):
        path = os.path.join(STATIC_JS_DIR, "article_list.js")
        with open(path) as f:
            content = f.read()
        self.assertNotIn("window.copyFeedUrl", content)

    def test_no_copyApiUrl_function(self):
        path = os.path.join(STATIC_JS_DIR, "article_list.js")
        with open(path) as f:
            content = f.read()
        self.assertNotIn("window.copyApiUrl", content)

    def test_no_copyFeedEmail_function(self):
        path = os.path.join(STATIC_JS_DIR, "article_list.js")
        with open(path) as f:
            content = f.read()
        self.assertNotIn("window.copyFeedEmail", content)


class TestFeedFormProviderFilterExtraction(TestCase):
    """Verify feed_form.html uses provider_filter.js instead of inline JS."""

    def setUp(self):
        self.client = Client()
        self.user = get_user_model().objects.create_user(
            username="ffprov", password="pass123"
        )
        self.client.login(username="ffprov", password="pass123")

    def test_includes_provider_filter_js(self):
        response = self.client.get("/feeds/new/")
        self.assertContains(response, "provider_filter.js")

    def test_no_inline_filter_script(self):
        response = self.client.get("/feeds/new/")
        content = response.content.decode()
        self.assertNotIn("function filterPresets", content)

    def test_has_provider_filter_config(self):
        response = self.client.get("/feeds/new/")
        content = response.content.decode()
        self.assertIn("data-provider-select", content)
        self.assertIn("data-preset-select", content)


class TestArticleFormProviderFilterExtraction(TestCase):
    """Verify article_form.html uses provider_filter.js instead of inline JS."""

    def setUp(self):
        self.client = Client()
        self.user = get_user_model().objects.create_user(
            username="afprov", password="pass123"
        )
        self.feed = Feed.objects.create(user=self.user, name="AF Prov Feed")
        self.client.login(username="afprov", password="pass123")

    def test_includes_provider_filter_js(self):
        response = self.client.get(f"/feeds/{self.feed.pk}/add/")
        self.assertContains(response, "provider_filter.js")

    def test_no_inline_filter_script(self):
        response = self.client.get(f"/feeds/{self.feed.pk}/add/")
        content = response.content.decode()
        self.assertNotIn("function filterOptions", content)

    def test_has_provider_filter_config(self):
        response = self.client.get(f"/feeds/{self.feed.pk}/add/")
        content = response.content.decode()
        self.assertIn("data-provider-select", content)
        self.assertIn("data-voice-select", content)
        self.assertIn("data-preset-select", content)


class TestVoiceSettingsProviderFilterExtraction(TestCase):
    """Verify article_voice_settings.html uses provider_filter.js."""

    def setUp(self):
        self.client = Client()
        self.user = get_user_model().objects.create_user(
            username="vsprov", password="pass123"
        )
        self.feed = Feed.objects.create(user=self.user, name="VS Prov Feed")
        self.article = Article.objects.create(
            feed=self.feed,
            title="VS Test Article",
            text_content="sample",
            status=Article.COMPLETED,
            audio_uuid=str(uuid.uuid4()),
        )
        self.client.login(username="vsprov", password="pass123")

    def test_includes_provider_filter_js(self):
        response = self.client.get(f"/articles/{self.article.pk}/voice/")
        self.assertContains(response, "provider_filter.js")

    def test_no_inline_filter_script(self):
        response = self.client.get(f"/articles/{self.article.pk}/voice/")
        content = response.content.decode()
        self.assertNotIn("function filterOptions", content)

    def test_has_provider_filter_config(self):
        response = self.client.get(f"/articles/{self.article.pk}/voice/")
        content = response.content.decode()
        self.assertIn("data-provider-select", content)
        self.assertIn("data-voice-select", content)
        self.assertIn("data-preset-select", content)
