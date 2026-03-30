"""Tests for HTTP method restrictions on function-based views.

Verifies that views return 405 Method Not Allowed for disallowed HTTP methods.
"""

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from accounts.models_profile import UserProfile
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


class SuperAdminTestBase(TestCase):
    """Base class for tests requiring super admin privileges."""

    def setUp(self):
        self.admin_user = User.objects.create_user(
            username="superadmin", password="password123"
        )
        self.admin_user.profile.is_super_admin = True
        self.admin_user.profile.is_approved = True
        self.admin_user.profile.save()
        self.client.login(username="superadmin", password="password123")

        self.target_user = User.objects.create_user(
            username="targetuser", password="password123"
        )


class UserApproveHttpMethodTest(SuperAdminTestBase):
    """Tests for user_approve view HTTP method restrictions."""

    def get_url(self):
        return reverse("user-approve", args=[self.target_user.id])

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
        self.assertEqual(response.status_code, 302)


class UserRevokeApprovalHttpMethodTest(SuperAdminTestBase):
    """Tests for user_revoke_approval view HTTP method restrictions."""

    def setUp(self):
        super().setUp()
        self.target_user.profile.is_approved = True
        self.target_user.profile.save()

    def get_url(self):
        return reverse("user-revoke-approval", args=[self.target_user.id])

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
        self.assertEqual(response.status_code, 302)


class UserPromoteHttpMethodTest(SuperAdminTestBase):
    """Tests for user_promote view HTTP method restrictions."""

    def get_url(self):
        return reverse("user-promote", args=[self.target_user.id])

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
        self.assertEqual(response.status_code, 302)


class UserDemoteHttpMethodTest(SuperAdminTestBase):
    """Tests for user_demote view HTTP method restrictions."""

    def setUp(self):
        super().setUp()
        # Need a second super admin so we can demote one
        self.target_user.profile.is_super_admin = True
        self.target_user.profile.is_approved = True
        self.target_user.profile.save()
        self.target_user.is_staff = True
        self.target_user.is_superuser = True
        self.target_user.save()

    def get_url(self):
        return reverse("user-demote", args=[self.target_user.id])

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
        self.assertEqual(response.status_code, 302)


class UserResetPasswordHttpMethodTest(SuperAdminTestBase):
    """Tests for user_reset_password view HTTP method restrictions."""

    def get_url(self):
        return reverse("user-reset-password", args=[self.target_user.id])

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


class MigrateEnvToConfigHttpMethodTest(SuperAdminTestBase):
    """Tests for migrate_env_to_config view HTTP method restrictions."""

    def get_url(self):
        return reverse("migrate-env-to-config")

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
        # GET redirects to global-config
        self.assertEqual(response.status_code, 302)

    def test_post_allowed(self):
        response = self.client.post(self.get_url())
        # POST redirects to global-config after migration
        self.assertEqual(response.status_code, 302)


class VoicePresetListHttpMethodTest(HttpMethodRestrictionTestBase):
    """Tests for voice_preset_list view HTTP method restrictions."""

    def get_url(self):
        return reverse("voice_preset_list")

    def test_post_returns_405(self):
        response = self.client.post(self.get_url())
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

    def test_get_allowed(self):
        response = self.client.get(self.get_url())
        self.assertEqual(response.status_code, 200)


class VoicePresetTestHttpMethodTest(HttpMethodRestrictionTestBase):
    """Tests for voice_preset_test view HTTP method restrictions."""

    def get_url(self):
        return reverse("voice_preset_test")

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
        # POST returns 400 (missing AJAX header/params) but NOT 405
        response = self.client.post(self.get_url())
        self.assertNotEqual(response.status_code, 405)


class VoicePresetSampleHttpMethodTest(HttpMethodRestrictionTestBase):
    """Tests for voice_preset_sample view HTTP method restrictions."""

    def setUp(self):
        super().setUp()
        self.preset = UserVoicePreset.objects.create(
            user=self.user, name="Sample Test", voice_id="nova", speed=1.0
        )

    def get_url(self):
        return reverse("voice_preset_sample", args=[self.preset.id])

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
        # GET renders the sample form (200)
        self.assertEqual(response.status_code, 200)

    def test_post_allowed(self):
        # POST returns 400 (missing/invalid form data) but NOT 405
        response = self.client.post(self.get_url())
        self.assertNotEqual(response.status_code, 405)


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
