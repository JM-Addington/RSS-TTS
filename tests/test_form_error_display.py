"""Tests for consistent form error display patterns across all templates.

All form templates should use 'invalid-feedback d-block' for field errors
and 'alert alert-danger' for non-field errors. No template should use
'text-danger' for field error display.

AIDEV-NOTE: These tests enforce the standard error display pattern from issue #233.
"""

# mypy: disable-error-code="attr-defined"

from django.contrib.auth import get_user_model
from django.test import Client, TestCase

from text_to_audio.models import Article, Feed, FollowedFeed

User = get_user_model()


class TestLoginFormErrorDisplay(TestCase):
    """Login form should use invalid-feedback d-block for field errors."""

    def setUp(self):
        self.client = Client()

    def test_field_errors_use_invalid_feedback(self):
        """POST empty credentials should show errors with invalid-feedback class."""
        response = self.client.post(
            "/accounts/login/",
            {"username": "", "password": ""},
        )
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn("invalid-feedback", content)
        self.assertNotIn("text-danger", content)

    def test_field_errors_have_d_block(self):
        """Field error divs must include d-block class."""
        response = self.client.post(
            "/accounts/login/",
            {"username": "", "password": ""},
        )
        content = response.content.decode()
        self.assertIn("invalid-feedback d-block", content)

    def test_field_errors_use_paragraph_tags(self):
        """Each error should be in a <p class="mb-0"> tag."""
        response = self.client.post(
            "/accounts/login/",
            {"username": "", "password": ""},
        )
        content = response.content.decode()
        self.assertIn('<p class="mb-0">', content)


class TestSignupFormErrorDisplay(TestCase):
    """Signup form should use invalid-feedback d-block for field errors."""

    def setUp(self):
        self.client = Client()

    def test_field_errors_use_invalid_feedback(self):
        """POST mismatched passwords should show errors with invalid-feedback."""
        response = self.client.post(
            "/accounts/signup/",
            {
                "username": "testuser",
                "password1": "short",
                "password2": "mismatch",
            },
        )
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn("invalid-feedback", content)
        self.assertNotIn("text-danger", content)

    def test_field_errors_have_d_block(self):
        """Field error divs must include d-block class."""
        response = self.client.post(
            "/accounts/signup/",
            {
                "username": "testuser",
                "password1": "short",
                "password2": "mismatch",
            },
        )
        content = response.content.decode()
        self.assertIn("invalid-feedback d-block", content)


class TestUserFormErrorDisplay(TestCase):
    """User create form should use invalid-feedback d-block for field errors."""

    def setUp(self):
        self.client = Client()
        self.admin = User.objects.create_superuser(
            username="admin", password="AdminPass123"
        )
        self.client.login(username="admin", password="AdminPass123")

    def test_field_errors_use_invalid_feedback(self):
        """POST empty username should show errors with invalid-feedback."""
        response = self.client.post(
            "/accounts/users/create/",
            {"username": "", "password1": "x", "password2": "y"},
        )
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn("invalid-feedback", content)
        self.assertNotIn("text-danger", content)

    def test_field_errors_have_d_block(self):
        """Field error divs must include d-block class."""
        response = self.client.post(
            "/accounts/users/create/",
            {"username": "", "password1": "x", "password2": "y"},
        )
        content = response.content.decode()
        self.assertIn("invalid-feedback d-block", content)


class TestFeedFormErrorDisplay(TestCase):
    """Feed form should use invalid-feedback d-block for all field errors."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username="feeduser", password="pass123"
        )
        self.client.login(username="feeduser", password="pass123")

    def test_name_field_errors_use_invalid_feedback_d_block(self):
        """Name field errors should use invalid-feedback d-block (not just invalid-feedback)."""
        response = self.client.post(
            "/feeds/new/",
            {"name": "", "tts_provider": "", "voice_mode": ""},
        )
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn("invalid-feedback d-block", content)

    def test_no_text_danger_for_field_errors(self):
        """Feed form should not use text-danger for field errors."""
        response = self.client.post(
            "/feeds/new/",
            {"name": "", "tts_provider": "", "voice_mode": ""},
        )
        content = response.content.decode()
        self.assertNotIn("text-danger", content)


class TestArticleFormErrorDisplay(TestCase):
    """Article form should use invalid-feedback d-block for field errors."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username="articleuser", password="pass123"
        )
        self.feed = Feed.objects.create(user=self.user, name="TestFeed")
        self.client.login(username="articleuser", password="pass123")

    def test_field_errors_use_invalid_feedback(self):
        """POST invalid URL should show field errors with invalid-feedback."""
        response = self.client.post(
            f"/feeds/{self.feed.pk}/add/",
            {"title": "", "source_url": "not-a-valid-url", "text_content": ""},
        )
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn("invalid-feedback", content)

    def test_no_text_danger_for_field_errors(self):
        """Article form should not use text-danger for field errors."""
        response = self.client.post(
            f"/feeds/{self.feed.pk}/add/",
            {"title": "", "source_url": "not-a-valid-url", "text_content": ""},
        )
        content = response.content.decode()
        self.assertNotIn("text-danger", content)

    def test_no_raw_errorlist(self):
        """Article form should not render Django's raw <ul class='errorlist'>."""
        response = self.client.post(
            f"/feeds/{self.feed.pk}/add/",
            {"title": "", "source_url": "not-a-valid-url", "text_content": ""},
        )
        content = response.content.decode()
        self.assertNotIn("errorlist", content)

    def test_template_has_no_text_danger(self):
        """Article form template source should not contain text-danger for field errors."""
        import os

        from django.conf import settings

        template_path = os.path.join(
            settings.BASE_DIR,
            "text_to_audio",
            "templates",
            "article_form.html",
        )
        with open(template_path) as f:
            content = f.read()
        self.assertNotIn("text-danger", content)
        self.assertIn("invalid-feedback d-block", content)


class TestVoicePresetFormErrorDisplay(TestCase):
    """Voice preset form should use invalid-feedback d-block for field errors."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username="presetuser", password="pass123"
        )
        self.client.login(username="presetuser", password="pass123")

    def test_field_errors_use_invalid_feedback(self):
        """POST empty preset should show errors with invalid-feedback."""
        response = self.client.post(
            "/presets/voice/new/",
            {"name": "", "voice_id": "", "speed": ""},
        )
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn("invalid-feedback", content)
        self.assertNotIn("text-danger", content)

    def test_field_errors_have_d_block(self):
        """Field error divs must include d-block class."""
        response = self.client.post(
            "/presets/voice/new/",
            {"name": "", "voice_id": "", "speed": ""},
        )
        content = response.content.decode()
        self.assertIn("invalid-feedback d-block", content)


class TestVoiceSampleFormErrorDisplay(TestCase):
    """Voice sample form should use invalid-feedback d-block for field errors."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username="sampleuser", password="pass123"
        )
        self.client.login(username="sampleuser", password="pass123")
        from text_to_audio.models import UserVoicePreset

        self.preset = UserVoicePreset.objects.create(
            user=self.user, name="TestPreset", voice_id="alloy", speed=1.0
        )

    def test_no_text_danger(self):
        """Voice sample form template should not contain text-danger class."""
        # GET the form and check the template doesn't have text-danger
        response = self.client.get(
            f"/presets/voice/{self.preset.pk}/sample/",
        )
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertNotIn("text-danger", content)


class TestVoicePreferencesErrorDisplay(TestCase):
    """Voice preferences form should iterate errors, not render raw."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username="prefuser", password="pass123"
        )
        self.client.login(username="prefuser", password="pass123")

    def test_no_text_danger(self):
        """Voice preferences template should not contain text-danger for field errors."""
        response = self.client.get("/preferences/voice/")
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertNotIn("text-danger", content)

    def test_errors_are_iterated(self):
        """Error display should use the standard form field partial."""
        import os

        from django.conf import settings

        template_path = os.path.join(
            settings.BASE_DIR,
            "text_to_audio",
            "templates",
            "text_to_audio",
            "voice_preferences.html",
        )
        with open(template_path) as f:
            content = f.read()
        # Should use the standard partial or inline error iteration
        self.assertTrue(
            "for error in" in content
            or '_form_field.html' in content,
            "Template should use _form_field.html partial or inline error iteration",
        )


class TestArticleVoiceSettingsErrorDisplay(TestCase):
    """Article voice settings form should iterate errors, not render raw."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username="voiceuser", password="pass123"
        )
        self.feed = Feed.objects.create(user=self.user, name="VoiceFeed")
        self.article = Article.objects.create(
            feed=self.feed,
            title="Test Article",
            text_content="content",
            status=Article.COMPLETED,
        )
        self.client.login(username="voiceuser", password="pass123")

    def test_no_text_danger(self):
        """Article voice settings should not use text-danger."""
        response = self.client.get(
            f"/articles/{self.article.pk}/voice/",
        )
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertNotIn("text-danger", content)

    def test_errors_are_iterated(self):
        """Error display should use the standard form field partial."""
        import os

        from django.conf import settings

        template_path = os.path.join(
            settings.BASE_DIR,
            "text_to_audio",
            "templates",
            "text_to_audio",
            "article_voice_settings.html",
        )
        with open(template_path) as f:
            content = f.read()
        # Should use the standard partial or inline error iteration
        self.assertTrue(
            "for error in" in content
            or '_form_field.html' in content,
            "Template should use _form_field.html partial or inline error iteration",
        )


class TestGlobalConfigErrorDisplay(TestCase):
    """Global config form should have field error display."""

    def setUp(self):
        self.client = Client()
        self.admin = User.objects.create_superuser(
            username="configadmin", password="AdminPass123"
        )
        self.client.login(username="configadmin", password="AdminPass123")

    def test_template_has_error_display(self):
        """Global config template should have invalid-feedback error display."""
        import os

        from django.conf import settings

        template_path = os.path.join(
            settings.BASE_DIR,
            "accounts",
            "templates",
            "accounts",
            "global_config.html",
        )
        with open(template_path) as f:
            content = f.read()
        self.assertIn("invalid-feedback d-block", content)

    def test_field_errors_shown_on_invalid_post(self):
        """POST invalid data should render errors with invalid-feedback."""
        response = self.client.post(
            "/accounts/config/",
            {"max_analysis_words": "not-a-number"},
        )
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn("invalid-feedback", content)


class TestFollowedFeedFormErrorDisplay(TestCase):
    """FollowedFeed form should use invalid-feedback d-block with <p class="mb-0"> for errors."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username="followuser", password="pass123"
        )
        self.feed = Feed.objects.create(user=self.user, name="DestFeed")
        self.client.login(username="followuser", password="pass123")

    def test_field_errors_use_invalid_feedback_d_block(self):
        """POST empty URL should show errors with invalid-feedback d-block."""
        response = self.client.post(
            "/followed-feeds/new/",
            {"url": "", "destination_feed": "", "is_active": "on"},
        )
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn("invalid-feedback d-block", content)
        self.assertNotIn("text-danger", content)

    def test_field_errors_use_paragraph_wrappers(self):
        """Each field error should be wrapped in <p class="mb-0">."""
        response = self.client.post(
            "/followed-feeds/new/",
            {"url": "", "destination_feed": "", "is_active": "on"},
        )
        content = response.content.decode()
        self.assertIn('<p class="mb-0">', content)

    def test_template_source_has_paragraph_wrappers(self):
        """Template source should contain <p class="mb-0"> in error blocks."""
        import os

        from django.conf import settings

        template_path = os.path.join(
            settings.BASE_DIR,
            "text_to_audio",
            "templates",
            "text_to_audio",
            "followedfeed_form.html",
        )
        with open(template_path) as f:
            content = f.read()
        self.assertIn('<p class="mb-0">', content)
        self.assertIn("invalid-feedback d-block", content)


class TestFormFieldPartialTemplate(TestCase):
    """The reusable _form_field.html partial should exist with standard patterns."""

    def test_partial_template_exists(self):
        """includes/_form_field.html should exist."""
        import os

        from django.conf import settings

        template_path = os.path.join(
            settings.BASE_DIR,
            "text_to_audio",
            "templates",
            "includes",
            "_form_field.html",
        )
        self.assertTrue(
            os.path.exists(template_path),
            f"Partial template not found at {template_path}",
        )

    def test_partial_has_standard_error_pattern(self):
        """Partial should contain invalid-feedback d-block and <p class="mb-0"> pattern."""
        import os

        from django.conf import settings

        template_path = os.path.join(
            settings.BASE_DIR,
            "text_to_audio",
            "templates",
            "includes",
            "_form_field.html",
        )
        with open(template_path) as f:
            content = f.read()
        self.assertIn("invalid-feedback d-block", content)
        self.assertIn('<p class="mb-0">', content)
        self.assertIn("for error in", content)

    def test_partial_has_help_text_support(self):
        """Partial should handle help_text."""
        import os

        from django.conf import settings

        template_path = os.path.join(
            settings.BASE_DIR,
            "text_to_audio",
            "templates",
            "includes",
            "_form_field.html",
        )
        with open(template_path) as f:
            content = f.read()
        self.assertIn("help_text", content)
