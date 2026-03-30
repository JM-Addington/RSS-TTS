"""Tests for HTTP method restrictions on function-based views.

Verifies that views return 405 Method Not Allowed for disallowed HTTP methods.
"""

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from text_to_audio.models import Article, Feed, UserVoicePreset


class HttpMethodRestrictionTestBase(TestCase):
    """Base class with shared setup for HTTP method restriction tests."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser", password="password123"
        )
        self.client.login(username="testuser", password="password123")


class VoicePreferencesHttpMethodTest(HttpMethodRestrictionTestBase):
    """Tests for voice_preferences view HTTP method restrictions."""

    def get_url(self):
        return reverse("voice_preferences")

    def test_put_returns_405(self):
        response = self.client.put(self.get_url())
        self.assertEqual(response.status_code, 405)

    def test_delete_returns_405(self):
        response = self.client.delete(self.get_url())
        self.assertEqual(response.status_code, 405)

    def test_patch_returns_405(self):
        response = self.client.patch(self.get_url())
        self.assertEqual(response.status_code, 405)

    def test_get_allowed(self):
        response = self.client.get(self.get_url())
        self.assertEqual(response.status_code, 200)


class VoicePresetCreateHttpMethodTest(HttpMethodRestrictionTestBase):
    """Tests for voice_preset_create view HTTP method restrictions."""

    def get_url(self):
        return reverse("voice_preset_create")

    def test_put_returns_405(self):
        response = self.client.put(self.get_url())
        self.assertEqual(response.status_code, 405)

    def test_delete_returns_405(self):
        response = self.client.delete(self.get_url())
        self.assertEqual(response.status_code, 405)

    def test_patch_returns_405(self):
        response = self.client.patch(self.get_url())
        self.assertEqual(response.status_code, 405)

    def test_get_allowed(self):
        response = self.client.get(self.get_url())
        self.assertEqual(response.status_code, 200)


class VoicePresetEditHttpMethodTest(HttpMethodRestrictionTestBase):
    """Tests for voice_preset_edit view HTTP method restrictions."""

    def setUp(self):
        super().setUp()
        self.preset = UserVoicePreset.objects.create(
            user=self.user, name="Test Preset", voice_id="nova", speed=1.0
        )

    def get_url(self):
        return reverse("voice_preset_edit", args=[self.preset.id])

    def test_put_returns_405(self):
        response = self.client.put(self.get_url())
        self.assertEqual(response.status_code, 405)

    def test_delete_returns_405(self):
        response = self.client.delete(self.get_url())
        self.assertEqual(response.status_code, 405)

    def test_patch_returns_405(self):
        response = self.client.patch(self.get_url())
        self.assertEqual(response.status_code, 405)

    def test_get_allowed(self):
        response = self.client.get(self.get_url())
        self.assertEqual(response.status_code, 200)


class VoicePresetDeleteHttpMethodTest(HttpMethodRestrictionTestBase):
    """Tests for voice_preset_delete view HTTP method restrictions."""

    def setUp(self):
        super().setUp()
        self.preset = UserVoicePreset.objects.create(
            user=self.user, name="Delete Test", voice_id="nova", speed=1.0
        )

    def get_url(self):
        return reverse("voice_preset_delete", args=[self.preset.id])

    def test_get_returns_405(self):
        response = self.client.get(self.get_url())
        self.assertEqual(response.status_code, 405)

    def test_put_returns_405(self):
        response = self.client.put(self.get_url())
        self.assertEqual(response.status_code, 405)

    def test_delete_returns_405(self):
        response = self.client.delete(self.get_url())
        self.assertEqual(response.status_code, 405)

    def test_patch_returns_405(self):
        response = self.client.patch(self.get_url())
        self.assertEqual(response.status_code, 405)

    def test_post_allowed(self):
        response = self.client.post(self.get_url())
        # POST should succeed (302 redirect after delete)
        self.assertEqual(response.status_code, 302)


class ArticleVoiceSettingsHttpMethodTest(HttpMethodRestrictionTestBase):
    """Tests for article_voice_settings view HTTP method restrictions."""

    def setUp(self):
        super().setUp()
        self.feed = Feed.objects.create(
            user=self.user,
            name="Test Feed",
        )
        self.article = Article.objects.create(
            feed=self.feed,
            title="Test Article",
        )

    def get_url(self):
        return reverse("article_voice_settings", args=[self.article.id])

    def test_put_returns_405(self):
        response = self.client.put(self.get_url())
        self.assertEqual(response.status_code, 405)

    def test_delete_returns_405(self):
        response = self.client.delete(self.get_url())
        self.assertEqual(response.status_code, 405)

    def test_patch_returns_405(self):
        response = self.client.patch(self.get_url())
        self.assertEqual(response.status_code, 405)

    def test_get_allowed(self):
        response = self.client.get(self.get_url())
        self.assertEqual(response.status_code, 200)
