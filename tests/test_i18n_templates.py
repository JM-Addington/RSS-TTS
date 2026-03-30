"""Tests for i18n template tags across all templates.

Verifies that:
1. Every template loads {% load i18n %}
2. Key user-facing strings are wrapped in {% trans %} or {% blocktrans %}
3. Templates still render correctly after i18n changes
"""

import os

from django.conf import settings
from django.test import Client, TestCase

# AIDEV-NOTE: All template paths relative to their app's templates dir
ACCOUNTS_TEMPLATE_DIR = os.path.join(settings.BASE_DIR, "accounts", "templates")
TTA_TEMPLATE_DIR = os.path.join(settings.BASE_DIR, "text_to_audio", "templates")

# Complete list of all template files that must have i18n
ALL_TEMPLATES = {
    # Accounts app
    "accounts/global_config.html": ACCOUNTS_TEMPLATE_DIR,
    "accounts/user_confirm_delete.html": ACCOUNTS_TEMPLATE_DIR,
    "accounts/user_form.html": ACCOUNTS_TEMPLATE_DIR,
    "accounts/user_management.html": ACCOUNTS_TEMPLATE_DIR,
    "accounts/user_reset_password.html": ACCOUNTS_TEMPLATE_DIR,
    # Registration
    "registration/login.html": TTA_TEMPLATE_DIR,
    "registration/logged_out.html": TTA_TEMPLATE_DIR,
    "registration/signup.html": TTA_TEMPLATE_DIR,
    # Partials
    "partials/_header.html": TTA_TEMPLATE_DIR,
    "partials/_footer.html": TTA_TEMPLATE_DIR,
    "partials/_nav.html": TTA_TEMPLATE_DIR,
    # Main
    "base.html": TTA_TEMPLATE_DIR,
    "index.html": TTA_TEMPLATE_DIR,
    "feed_list.html": TTA_TEMPLATE_DIR,
    "feed_form.html": TTA_TEMPLATE_DIR,
    "feed_confirm_delete.html": TTA_TEMPLATE_DIR,
    # Article
    "article_form.html": TTA_TEMPLATE_DIR,
    "article_list.html": TTA_TEMPLATE_DIR,
    "article_confirm_delete.html": TTA_TEMPLATE_DIR,
    "text_to_audio/article_detail.html": TTA_TEMPLATE_DIR,
    "text_to_audio/article_voice_settings.html": TTA_TEMPLATE_DIR,
    "text_to_audio/article_confirm_delete.html": TTA_TEMPLATE_DIR,
    # Voice/Preset
    "text_to_audio/voice_preferences.html": TTA_TEMPLATE_DIR,
    "text_to_audio/voice_preset_list.html": TTA_TEMPLATE_DIR,
    "text_to_audio/voice_preset_form.html": TTA_TEMPLATE_DIR,
    "text_to_audio/voice_preset_confirm_delete.html": TTA_TEMPLATE_DIR,
    "text_to_audio/voice_sample_form.html": TTA_TEMPLATE_DIR,
    # Other
    "text_to_audio/cost_analytics.html": TTA_TEMPLATE_DIR,
    "text_to_audio/followedfeed_list.html": TTA_TEMPLATE_DIR,
    "text_to_audio/followedfeed_form.html": TTA_TEMPLATE_DIR,
    "text_to_audio/followedfeed_confirm_delete.html": TTA_TEMPLATE_DIR,
}


def _read_template(relative_path, base_dir):
    """Read a template file and return its contents."""
    full_path = os.path.join(base_dir, relative_path)
    with open(full_path) as f:
        return f.read()


class TestI18nTemplateLoading(TestCase):
    """Verify all templates load the i18n module."""

    def test_all_templates_load_i18n(self):
        """Every template must contain {% load i18n %}."""
        missing = []
        for template_path, base_dir in ALL_TEMPLATES.items():
            content = _read_template(template_path, base_dir)
            if "{% load i18n %}" not in content and "{% load i18n " not in content:
                missing.append(template_path)
        self.assertEqual(
            missing,
            [],
            f"Templates missing {{% load i18n %}}: {missing}",
        )


class TestI18nTransTags(TestCase):
    """Spot-check that key strings are wrapped in trans tags."""

    def _assert_has_trans(self, content, string, template_name):
        """Assert that a string appears inside a {% trans %} tag."""
        patterns = [
            f'{{% trans "{string}" %}}',
            f"{{% trans '{string}' %}}",
        ]
        found = any(p in content for p in patterns)
        self.assertTrue(
            found,
            f'String "{string}" not wrapped in {{% trans %}} in {template_name}',
        )

    def _assert_has_trans_or_blocktrans(self, content, string, template_name):
        """Assert that a string is in a trans or blocktrans tag."""
        patterns = [
            f'{{% trans "{string}" %}}',
            f"{{% trans '{string}' %}}",
            "{% blocktrans",
        ]
        found = any(p in content for p in patterns)
        self.assertTrue(
            found,
            f'String "{string}" not i18n-wrapped in {template_name}',
        )

    # --- Registration templates ---

    def test_login_template_trans_tags(self):
        content = _read_template("registration/login.html", TTA_TEMPLATE_DIR)
        self._assert_has_trans(content, "Login", "login.html")
        # Username/Password labels are rendered via _form_field.html partial
        # which uses {{ field.label }} — i18n is handled at the form level

    def test_logged_out_template_trans_tags(self):
        content = _read_template("registration/logged_out.html", TTA_TEMPLATE_DIR)
        self._assert_has_trans(content, "Logged Out", "logged_out.html")
        self._assert_has_trans(content, "You have been logged out.", "logged_out.html")
        self._assert_has_trans(content, "Login again", "logged_out.html")

    def test_signup_template_trans_tags(self):
        content = _read_template("registration/signup.html", TTA_TEMPLATE_DIR)
        self._assert_has_trans(content, "Sign Up", "signup.html")
        # Username label rendered via _form_field.html partial — i18n at form level
        self._assert_has_trans(content, "Create Account", "signup.html")

    # --- Partials ---

    def test_nav_template_trans_tags(self):
        content = _read_template("partials/_nav.html", TTA_TEMPLATE_DIR)
        self._assert_has_trans(content, "My Feeds", "_nav.html")
        self._assert_has_trans(content, "Costs", "_nav.html")
        self._assert_has_trans(content, "Admin", "_nav.html")
        self._assert_has_trans(content, "Logout", "_nav.html")
        self._assert_has_trans(content, "Login", "_nav.html")
        self._assert_has_trans(content, "Voice Settings", "_nav.html")

    def test_header_template_trans_tags(self):
        content = _read_template("partials/_header.html", TTA_TEMPLATE_DIR)
        self._assert_has_trans(content, "Welcome to RSS-TTS", "_header.html")

    # --- Main templates ---

    def test_index_template_trans_tags(self):
        content = _read_template("index.html", TTA_TEMPLATE_DIR)
        self._assert_has_trans(content, "Home", "index.html")

    def test_feed_list_template_trans_tags(self):
        content = _read_template("feed_list.html", TTA_TEMPLATE_DIR)
        self._assert_has_trans(content, "My Feeds", "feed_list.html")
        self._assert_has_trans(content, "Create New Feed", "feed_list.html")
        self._assert_has_trans(content, "Add Article", "feed_list.html")
        self._assert_has_trans(content, "View Articles", "feed_list.html")

    def test_feed_form_template_trans_tags(self):
        content = _read_template("feed_form.html", TTA_TEMPLATE_DIR)
        self._assert_has_trans(content, "Feed Name", "feed_form.html")
        self._assert_has_trans(content, "Cancel", "feed_form.html")
        self._assert_has_trans(content, "TTS Provider", "feed_form.html")

    def test_feed_confirm_delete_template_trans_tags(self):
        content = _read_template("feed_confirm_delete.html", TTA_TEMPLATE_DIR)
        self._assert_has_trans(content, "Delete Feed", "feed_confirm_delete.html")
        self._assert_has_trans(content, "Cancel", "feed_confirm_delete.html")

    # --- Article templates ---

    def test_article_form_template_trans_tags(self):
        content = _read_template("article_form.html", TTA_TEMPLATE_DIR)
        self._assert_has_trans(content, "Voice Settings", "article_form.html")
        self._assert_has_trans(content, "Convert to Audio", "article_form.html")
        self._assert_has_trans(content, "TTS Provider", "article_form.html")

    def test_article_list_template_trans_tags(self):
        content = _read_template("article_list.html", TTA_TEMPLATE_DIR)
        self._assert_has_trans(content, "Your Articles", "article_list.html")
        self._assert_has_trans(content, "Add Article", "article_list.html")
        self._assert_has_trans(content, "Title", "article_list.html")
        self._assert_has_trans(content, "Status", "article_list.html")

    def test_article_confirm_delete_template_trans_tags(self):
        content = _read_template("article_confirm_delete.html", TTA_TEMPLATE_DIR)
        self._assert_has_trans(
            content, "Confirm Delete Article", "article_confirm_delete.html"
        )
        self._assert_has_trans(content, "Confirm Delete", "article_confirm_delete.html")
        self._assert_has_trans(content, "Cancel", "article_confirm_delete.html")

    def test_article_detail_template_trans_tags(self):
        content = _read_template("text_to_audio/article_detail.html", TTA_TEMPLATE_DIR)
        self._assert_has_trans(content, "Article Details", "article_detail.html")
        self._assert_has_trans(content, "Source URL", "article_detail.html")
        self._assert_has_trans(content, "Regenerate Audio", "article_detail.html")

    def test_article_voice_settings_template_trans_tags(self):
        content = _read_template(
            "text_to_audio/article_voice_settings.html", TTA_TEMPLATE_DIR
        )
        self._assert_has_trans(
            content, "Voice Settings for Article", "article_voice_settings.html"
        )
        self._assert_has_trans(content, "Save Settings", "article_voice_settings.html")

    # --- Voice/Preset templates ---

    def test_voice_preferences_template_trans_tags(self):
        content = _read_template(
            "text_to_audio/voice_preferences.html", TTA_TEMPLATE_DIR
        )
        self._assert_has_trans(content, "Voice Preferences", "voice_preferences.html")
        self._assert_has_trans(content, "Save Preferences", "voice_preferences.html")

    def test_voice_preset_list_template_trans_tags(self):
        content = _read_template(
            "text_to_audio/voice_preset_list.html", TTA_TEMPLATE_DIR
        )
        self._assert_has_trans(content, "Your Voice Presets", "voice_preset_list.html")
        self._assert_has_trans(content, "Create New Preset", "voice_preset_list.html")

    def test_voice_preset_confirm_delete_template_trans_tags(self):
        content = _read_template(
            "text_to_audio/voice_preset_confirm_delete.html", TTA_TEMPLATE_DIR
        )
        self._assert_has_trans(
            content, "Delete Voice Preset", "voice_preset_confirm_delete.html"
        )
        self._assert_has_trans(
            content, "Confirm Delete", "voice_preset_confirm_delete.html"
        )

    def test_voice_sample_form_template_trans_tags(self):
        content = _read_template(
            "text_to_audio/voice_sample_form.html", TTA_TEMPLATE_DIR
        )
        self._assert_has_trans(content, "Generate Sample", "voice_sample_form.html")
        self._assert_has_trans(content, "Back", "voice_sample_form.html")

    # --- Accounts templates ---

    def test_global_config_template_trans_tags(self):
        content = _read_template("accounts/global_config.html", ACCOUNTS_TEMPLATE_DIR)
        self._assert_has_trans(content, "Global Configuration", "global_config.html")
        self._assert_has_trans(content, "Save Configuration", "global_config.html")

    def test_user_management_template_trans_tags(self):
        content = _read_template("accounts/user_management.html", ACCOUNTS_TEMPLATE_DIR)
        self._assert_has_trans(content, "User Management", "user_management.html")
        self._assert_has_trans(content, "Create New User", "user_management.html")
        self._assert_has_trans(content, "Username", "user_management.html")

    def test_user_confirm_delete_template_trans_tags(self):
        content = _read_template(
            "accounts/user_confirm_delete.html", ACCOUNTS_TEMPLATE_DIR
        )
        self._assert_has_trans(content, "Delete User", "user_confirm_delete.html")
        self._assert_has_trans(content, "Yes, Delete User", "user_confirm_delete.html")
        self._assert_has_trans(content, "Cancel", "user_confirm_delete.html")

    def test_user_form_template_trans_tags(self):
        content = _read_template("accounts/user_form.html", ACCOUNTS_TEMPLATE_DIR)
        # Username/Password labels rendered via _form_field.html partial — i18n at form level
        self._assert_has_trans(content, "Cancel", "user_form.html")

    def test_user_reset_password_template_trans_tags(self):
        content = _read_template(
            "accounts/user_reset_password.html", ACCOUNTS_TEMPLATE_DIR
        )
        # "New Password" label rendered via _form_field.html partial — i18n at form level
        self._assert_has_trans(content, "Reset Password", "user_reset_password.html")
        self._assert_has_trans(content, "Cancel", "user_reset_password.html")

    # --- Other templates ---

    def test_cost_analytics_template_trans_tags(self):
        content = _read_template("text_to_audio/cost_analytics.html", TTA_TEMPLATE_DIR)
        self._assert_has_trans(content, "Cost Analytics", "cost_analytics.html")
        self._assert_has_trans(content, "Total Cost", "cost_analytics.html")
        self._assert_has_trans(content, "Cost by Model", "cost_analytics.html")

    def test_followedfeed_list_template_trans_tags(self):
        content = _read_template(
            "text_to_audio/followedfeed_list.html", TTA_TEMPLATE_DIR
        )
        self._assert_has_trans(content, "My Followed Feeds", "followedfeed_list.html")
        self._assert_has_trans(
            content, "Add New Followed Feed", "followedfeed_list.html"
        )

    def test_followedfeed_confirm_delete_template_trans_tags(self):
        content = _read_template(
            "text_to_audio/followedfeed_confirm_delete.html", TTA_TEMPLATE_DIR
        )
        self._assert_has_trans(
            content, "Confirm Deletion", "followedfeed_confirm_delete.html"
        )
        self._assert_has_trans(
            content, "Yes, Delete", "followedfeed_confirm_delete.html"
        )
        self._assert_has_trans(content, "Cancel", "followedfeed_confirm_delete.html")


class TestI18nRenderIntegrity(TestCase):
    """Verify templates still render correctly after i18n changes."""

    def setUp(self):
        self.client = Client()

    def test_home_page_renders(self):
        """Home page should still render with i18n tags."""
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "RSS-TTS")

    def test_login_page_renders(self):
        """Login page should still render with i18n tags."""
        response = self.client.get("/accounts/login/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Login")
        self.assertContains(response, "Username")
        self.assertContains(response, "Password")

    def test_signup_page_renders(self):
        """Signup page should still render with i18n tags."""
        response = self.client.get("/accounts/signup/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Sign Up")
        self.assertContains(response, "Username")

    def test_logged_out_template_has_i18n(self):
        """Logged out template file should have i18n tags (static check)."""
        # The logout POST redirects to home, so we verify the template file directly
        import os

        template_path = os.path.join(
            TTA_TEMPLATE_DIR, "registration", "logged_out.html"
        )
        with open(template_path) as f:
            content = f.read()
        self.assertIn("{% load i18n %}", content)
        self.assertIn('{% trans "Logged Out" %}', content)
