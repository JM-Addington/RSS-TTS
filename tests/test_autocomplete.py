"""Tests for password manager autofill prevention on non-login forms.

Verifies that forms on non-login pages include appropriate attributes to prevent
password managers (Bitwarden, LastPass, 1Password) from auto-filling fields.
See: https://github.com/JM-Addington/RSS-TTS/issues/ (email fields autofill bug)
"""

# mypy: disable-error-code="attr-defined"

from django.contrib.auth import get_user_model
from django.test import Client, TestCase

from text_to_audio.models import Feed


# AIDEV-NOTE: Password manager ignore attrs used across all non-login forms
PASSWORD_MANAGER_ATTRS = [
    'autocomplete="off"',
    'data-form-type="other"',
]


class TestFeedListAutocomplete(TestCase):
    """Test that feed list page prevents password manager autofill."""

    def setUp(self):
        """Create test client, user, and feed with inbound email."""
        self.client = Client()
        self.user = get_user_model().objects.create_user(
            username="autocomplete_test", password="pass123"
        )
        self.feed = Feed.objects.create(
            user=self.user,
            name="Test Feed",
            inbound_email="test-feed@mg.example.com",
        )
        self.client.login(username="autocomplete_test", password="pass123")

    def test_feed_list_email_field_has_autocomplete_off(self):
        """Email display field on feed list should have autocomplete='off'."""
        response = self.client.get("/feeds/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'autocomplete="off"')

    def test_feed_list_email_field_has_password_manager_attrs(self):
        """Email display field should have password manager ignore attributes."""
        response = self.client.get("/feeds/")
        content = response.content.decode()
        self.assertIn('data-lpignore="true"', content)
        self.assertIn("data-1p-ignore", content)
        self.assertIn('data-form-type="other"', content)

    def test_feed_list_rss_url_field_has_autocomplete_off(self):
        """RSS URL readonly field on feed list should have autocomplete='off'."""
        response = self.client.get("/feeds/")
        content = response.content.decode()
        # The RSS URL field should also prevent autofill
        self.assertIn('autocomplete="off"', content)


class TestArticleListAutocomplete(TestCase):
    """Test that article list page prevents password manager autofill."""

    def setUp(self):
        """Create test client, user, and feed with inbound email."""
        self.client = Client()
        self.user = get_user_model().objects.create_user(
            username="autocomplete_test2", password="pass123"
        )
        self.feed = Feed.objects.create(
            user=self.user,
            name="Test Feed",
            inbound_email="test-feed-2@mg.example.com",
        )
        self.client.login(username="autocomplete_test2", password="pass123")

    def test_article_list_email_field_has_autocomplete_off(self):
        """Email display field on article list should have autocomplete='off'."""
        response = self.client.get(f"/feeds/{self.feed.pk}/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'autocomplete="off"')

    def test_article_list_email_field_has_password_manager_attrs(self):
        """Email field should have all password manager ignore attributes."""
        response = self.client.get(f"/feeds/{self.feed.pk}/")
        content = response.content.decode()
        self.assertIn('data-lpignore="true"', content)
        self.assertIn("data-1p-ignore", content)
        self.assertIn('data-form-type="other"', content)

    def test_article_list_feed_url_has_autocomplete_off(self):
        """Feed URL readonly field should have autocomplete='off'."""
        response = self.client.get(f"/feeds/{self.feed.pk}/")
        content = response.content.decode()
        # Feed URL and API URL fields should also have autocomplete off
        self.assertIn('autocomplete="off"', content)


class TestFeedFormAutocomplete(TestCase):
    """Test that feed create/edit form prevents password manager autofill."""

    def setUp(self):
        """Create test client and user."""
        self.client = Client()
        self.user = get_user_model().objects.create_user(
            username="feedform_test", password="pass123"
        )
        self.client.login(username="feedform_test", password="pass123")

    def test_feed_create_form_has_autocomplete_off(self):
        """Feed creation form should have autocomplete='off' on the form tag."""
        response = self.client.get("/feeds/new/")
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn('autocomplete="off"', content)


class TestArticleFormAutocomplete(TestCase):
    """Test that article submission form prevents password manager autofill."""

    def setUp(self):
        """Create test client, user, and feed."""
        self.client = Client()
        self.user = get_user_model().objects.create_user(
            username="articleform_test", password="pass123"
        )
        self.feed = Feed.objects.create(user=self.user, name="Test Feed")
        self.client.login(username="articleform_test", password="pass123")

    def test_article_form_has_autocomplete_off(self):
        """Article submission form should have autocomplete='off' on the form tag."""
        response = self.client.get(f"/feeds/{self.feed.pk}/add/")
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn('autocomplete="off"', content)


class TestUserFormAutocomplete(TestCase):
    """Test that user management forms prevent password manager autofill."""

    def setUp(self):
        """Create test client and superadmin user."""
        self.client = Client()
        self.user = get_user_model().objects.create_superuser(
            username="admin_test", password="pass123"
        )
        self.client.login(username="admin_test", password="pass123")

    def test_user_create_form_has_autocomplete_off(self):
        """User creation form should have autocomplete='off' on the form tag."""
        response = self.client.get("/accounts/users/create/")
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn('autocomplete="off"', content)

    def test_user_reset_password_form_has_autocomplete_off(self):
        """Password reset form should have autocomplete='off' on the form tag."""
        target_user = get_user_model().objects.create_user(
            username="target_user", password="pass123"
        )
        response = self.client.get(
            f"/accounts/users/{target_user.pk}/reset-password/"
        )
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn('autocomplete="off"', content)


class TestLoginFormKeepsAutocomplete(TestCase):
    """Test that login form does NOT disable autocomplete (it should work there)."""

    def test_login_form_allows_autocomplete(self):
        """Login page form tag should NOT have autocomplete='off' to allow password managers."""
        client = Client()
        response = client.get("/accounts/login/")
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        # Verify the login form tag specifically does not include autocomplete="off"
        self.assertIn("<form", content)
        # The login form's <form> tag should not contain autocomplete="off"
        import re

        form_tags = re.findall(r"<form[^>]*>", content)
        for form_tag in form_tags:
            self.assertNotIn('autocomplete="off"', form_tag)
