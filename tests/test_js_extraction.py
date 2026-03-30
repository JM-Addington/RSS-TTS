"""Tests verifying inline JS has been extracted to external static files."""

# mypy: disable-error-code="attr-defined"

import os
import re
import uuid

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import Client, TestCase

from text_to_audio.models import Article, Feed


class TestStaticJSFilesExist(TestCase):
    """Verify that external JS files exist at expected paths."""

    STATIC_JS_DIR = os.path.join(
        settings.BASE_DIR,
        "text_to_audio",
        "static",
        "text_to_audio",
        "js",
    )

    ACCOUNTS_JS_DIR = os.path.join(
        settings.BASE_DIR,
        "accounts",
        "static",
        "accounts",
        "js",
    )

    def test_article_list_js_exists(self):
        path = os.path.join(self.STATIC_JS_DIR, "article_list.js")
        self.assertTrue(os.path.isfile(path), f"Missing {path}")

    def test_voice_preset_form_js_exists(self):
        path = os.path.join(self.STATIC_JS_DIR, "voice_preset_form.js")
        self.assertTrue(os.path.isfile(path), f"Missing {path}")

    def test_cost_analytics_js_exists(self):
        path = os.path.join(self.STATIC_JS_DIR, "cost_analytics.js")
        self.assertTrue(os.path.isfile(path), f"Missing {path}")

    def test_clipboard_utils_js_exists(self):
        path = os.path.join(self.STATIC_JS_DIR, "clipboard_utils.js")
        self.assertTrue(os.path.isfile(path), f"Missing {path}")

    def test_provider_filter_js_exists(self):
        path = os.path.join(self.STATIC_JS_DIR, "provider_filter.js")
        self.assertTrue(os.path.isfile(path), f"Missing {path}")

    def test_global_config_js_exists(self):
        path = os.path.join(self.ACCOUNTS_JS_DIR, "global_config.js")
        self.assertTrue(os.path.isfile(path), f"Missing {path}")


class TestArticleListJSExtraction(TestCase):
    """Verify article_list.html references external JS and passes data via data-* attrs."""

    def setUp(self):
        self.client = Client()
        self.user = get_user_model().objects.create_user(
            username="jstest", password="pass123"
        )
        self.feed = Feed.objects.create(user=self.user, name="JS Test Feed")
        self.article = Article.objects.create(
            feed=self.feed,
            title="JS Test Article",
            text_content="sample",
            status=Article.COMPLETED,
            audio_uuid=str(uuid.uuid4()),
        )
        self.client.login(username="jstest", password="pass123")

    def test_references_external_js_file(self):
        response = self.client.get(f"/feeds/{self.feed.pk}/")
        self.assertContains(response, "text_to_audio/js/article_list.js")

    def test_has_js_config_element(self):
        response = self.client.get(f"/feeds/{self.feed.pk}/")
        content = response.content.decode()
        self.assertIn('id="js-config"', content)

    def test_js_config_has_csrf_token(self):
        response = self.client.get(f"/feeds/{self.feed.pk}/")
        content = response.content.decode()
        self.assertIn("data-csrf-token", content)

    def test_js_config_has_feed_id(self):
        response = self.client.get(f"/feeds/{self.feed.pk}/")
        content = response.content.decode()
        self.assertIn(f'data-feed-id="{self.feed.pk}"', content)

    def test_no_large_inline_script(self):
        """No inline <script> block should exceed 20 lines (excluding JSON blocks)."""
        response = self.client.get(f"/feeds/{self.feed.pk}/")
        content = response.content.decode()
        # Find all <script> blocks (not type="application/json")
        script_blocks = re.findall(
            r"<script(?:\s[^>]*)?>(.+?)</script>",
            content,
            re.DOTALL,
        )
        for block in script_blocks:
            lines = block.strip().split("\n")
            self.assertLessEqual(
                len(lines),
                20,
                f"Inline script block has {len(lines)} lines (max 20):\n{block[:200]}...",
            )


class TestVoicePresetFormJSExtraction(TestCase):
    """Verify voice_preset_form.html references external JS."""

    def setUp(self):
        self.client = Client()
        self.user = get_user_model().objects.create_user(
            username="vptest", password="pass123"
        )
        self.client.login(username="vptest", password="pass123")

    def test_references_external_js_file(self):
        response = self.client.get("/presets/voice/new/")
        self.assertContains(response, "text_to_audio/js/voice_preset_form.js")

    def test_has_js_config_element(self):
        response = self.client.get("/presets/voice/new/")
        content = response.content.decode()
        self.assertIn('id="js-config"', content)

    def test_js_config_has_test_url(self):
        response = self.client.get("/presets/voice/new/")
        content = response.content.decode()
        self.assertIn("data-test-url", content)

    def test_no_large_inline_script(self):
        response = self.client.get("/presets/voice/new/")
        content = response.content.decode()
        script_blocks = re.findall(
            r"<script(?:\s[^>]*)?>(.+?)</script>",
            content,
            re.DOTALL,
        )
        for block in script_blocks:
            lines = block.strip().split("\n")
            self.assertLessEqual(
                len(lines),
                20,
                f"Inline script block has {len(lines)} lines (max 20):\n{block[:200]}...",
            )


class TestCostAnalyticsJSExtraction(TestCase):
    """Verify cost_analytics.html references external JS and passes chart data as JSON."""

    def setUp(self):
        self.client = Client()
        self.user = get_user_model().objects.create_user(
            username="costtest", password="pass123"
        )
        self.client.login(username="costtest", password="pass123")

    def test_references_external_js_file(self):
        response = self.client.get("/costs/")
        self.assertContains(response, "text_to_audio/js/cost_analytics.js")

    def test_has_chart_data_json_block(self):
        response = self.client.get("/costs/")
        content = response.content.decode()
        self.assertIn('id="chart-data"', content)
        self.assertIn('type="application/json"', content)

    def test_no_large_inline_script(self):
        response = self.client.get("/costs/")
        content = response.content.decode()
        # Find all script blocks excluding type="application/json"
        script_blocks = re.findall(
            r'<script(?:\s(?!type="application/json")[^>]*)?>(.+?)</script>',
            content,
            re.DOTALL,
        )
        for block in script_blocks:
            lines = block.strip().split("\n")
            self.assertLessEqual(
                len(lines),
                20,
                f"Inline script block has {len(lines)} lines (max 20):\n{block[:200]}...",
            )


class TestGlobalConfigJSExtraction(TestCase):
    """Verify global_config.html uses external JS instead of inline onclick."""

    ACCOUNTS_JS_DIR = os.path.join(
        settings.BASE_DIR,
        "accounts",
        "static",
        "accounts",
        "js",
    )

    TEMPLATE_PATH = os.path.join(
        settings.BASE_DIR,
        "accounts",
        "templates",
        "accounts",
        "global_config.html",
    )

    def setUp(self):
        self.client = Client()
        self.user = get_user_model().objects.create_user(
            username="gctest", password="pass123", is_superuser=True, is_staff=True
        )
        self.client.login(username="gctest", password="pass123")

    def test_static_js_file_exists(self):
        path = os.path.join(self.ACCOUNTS_JS_DIR, "global_config.js")
        self.assertTrue(os.path.isfile(path), f"Missing {path}")

    def test_template_references_external_js(self):
        with open(self.TEMPLATE_PATH) as f:
            content = f.read()
        self.assertIn("accounts/js/global_config.js", content)

    def test_no_inline_onclick_in_template(self):
        with open(self.TEMPLATE_PATH) as f:
            content = f.read()
        self.assertNotIn("onclick=", content)

    def test_js_file_has_addEventListener(self):
        path = os.path.join(self.ACCOUNTS_JS_DIR, "global_config.js")
        with open(path) as f:
            content = f.read()
        self.assertIn("addEventListener", content)
