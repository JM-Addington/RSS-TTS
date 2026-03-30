from django.contrib.auth.models import User
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from appconfig.models import GlobalConfig


class UserProfileTests(TestCase):
    """Test cases for the UserProfile model."""

    def test_first_user_becomes_super_admin(self):
        """Test that the first user created becomes a super admin."""
        user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass123"
        )

        self.assertTrue(user.is_super_admin)
        self.assertTrue(user.is_approved)
        self.assertTrue(user.is_staff)
        self.assertTrue(user.is_superuser)

    def test_second_user_is_not_auto_approved(self):
        """Test that subsequent users are not auto-approved."""
        # Create first user
        User.objects.create_user(
            username="firstuser", email="first@example.com", password="testpass123"
        )

        # Create second user
        second_user = User.objects.create_user(
            username="seconduser", email="second@example.com", password="testpass123"
        )

        self.assertFalse(second_user.is_super_admin)
        self.assertFalse(second_user.is_approved)
        self.assertFalse(second_user.is_staff)
        self.assertFalse(second_user.is_superuser)

    def test_can_manage_users_method(self):
        """Test the can_manage_users method."""
        # Create super admin
        super_admin = User.objects.create_user(
            username="superadmin", email="admin@example.com", password="testpass123"
        )

        # Create regular user
        regular_user = User.objects.create_user(
            username="regular", email="regular@example.com", password="testpass123"
        )

        self.assertTrue(super_admin.can_manage_users())
        self.assertFalse(regular_user.can_manage_users())


@override_settings(
    MIDDLEWARE=[
        "django.middleware.security.SecurityMiddleware",
        "django.contrib.sessions.middleware.SessionMiddleware",
        "django.middleware.common.CommonMiddleware",
        "django.middleware.csrf.CsrfViewMiddleware",
        "django.contrib.auth.middleware.AuthenticationMiddleware",
        "django.contrib.messages.middleware.MessageMiddleware",
        "django.middleware.clickjacking.XFrameOptionsMiddleware",
    ]
)
class UserManagementViewTests(TestCase):
    """Test cases for user management views."""

    def setUp(self):
        """Set up test data."""
        self.client = Client()
        self.super_admin = User.objects.create_user(
            username="admin", email="admin@example.com", password="testpass123"
        )
        self.regular_user = User.objects.create_user(
            username="regular", email="regular@example.com", password="testpass123"
        )

    def test_user_management_requires_super_admin(self):
        """Test that user management requires super admin privileges."""
        # Test unauthenticated access
        response = self.client.get(reverse("user-management"))
        self.assertEqual(response.status_code, 403)

        # Test regular user access
        self.client.login(username="regular", password="testpass123")
        response = self.client.get(reverse("user-management"))
        self.assertEqual(response.status_code, 403)

        # Test super admin access
        self.client.login(username="admin", password="testpass123")
        response = self.client.get(reverse("user-management"))
        self.assertEqual(response.status_code, 200)

    def test_user_approval_function(self):
        """Test user approval functionality."""
        self.client.login(username="admin", password="testpass123")

        # Regular user should not be approved initially
        self.assertFalse(self.regular_user.is_approved)

        # Approve the user
        response = self.client.get(reverse("user-approve", args=[self.regular_user.id]))
        self.assertEqual(response.status_code, 302)  # Redirect after approval

        # Check that user is now approved
        self.regular_user.refresh_from_db()
        self.assertTrue(self.regular_user.is_approved)

    def test_user_approval_revocation(self):
        """Test revoking user approval."""
        self.client.login(username="admin", password="testpass123")

        # First approve the user
        self.regular_user.profile.is_approved = True
        self.regular_user.profile.save()

        # Revoke approval
        response = self.client.get(
            reverse("user-revoke-approval", args=[self.regular_user.id])
        )
        self.assertEqual(response.status_code, 302)  # Redirect after revocation

        # Check that user approval is revoked
        self.regular_user.refresh_from_db()
        self.assertFalse(self.regular_user.is_approved)

    def test_cannot_revoke_super_admin_approval(self):
        """Test that super admin approval cannot be revoked."""
        self.client.login(username="admin", password="testpass123")

        # Try to revoke super admin approval
        response = self.client.get(
            reverse("user-revoke-approval", args=[self.super_admin.id])
        )
        self.assertEqual(response.status_code, 302)  # Redirect

        # Check that super admin is still approved
        self.super_admin.refresh_from_db()
        self.assertTrue(self.super_admin.is_approved)

    def test_user_creation_by_admin(self):
        """Test that super admin can create new users."""
        self.client.login(username="admin", password="testpass123")

        response = self.client.post(
            reverse("user-create"),
            {
                "username": "newuser",
                "password1": "complexpass123",
                "password2": "complexpass123",
            },
        )

        self.assertEqual(response.status_code, 302)  # Redirect after creation

        # Check that user was created
        new_user = User.objects.get(username="newuser")
        self.assertFalse(new_user.is_super_admin)
        self.assertFalse(new_user.is_approved)

    def test_promote_user_to_super_admin(self):
        """Test promoting a user via view."""
        self.client.login(username="admin", password="testpass123")

        response = self.client.get(reverse("user-promote", args=[self.regular_user.id]))
        self.assertEqual(response.status_code, 302)

        self.regular_user.refresh_from_db()
        self.assertTrue(self.regular_user.is_super_admin)
        self.assertTrue(self.regular_user.is_approved)
        self.assertTrue(self.regular_user.is_staff)
        self.assertTrue(self.regular_user.is_superuser)

    def test_demote_user_from_super_admin(self):
        """Test demoting a user via view."""
        self.client.login(username="admin", password="testpass123")

        self.regular_user.profile.is_super_admin = True
        self.regular_user.profile.is_approved = True
        self.regular_user.profile.save()
        self.regular_user.is_staff = True
        self.regular_user.is_superuser = True
        self.regular_user.save()

        response = self.client.get(reverse("user-demote", args=[self.regular_user.id]))
        self.assertEqual(response.status_code, 302)

        self.regular_user.refresh_from_db()
        self.assertFalse(self.regular_user.is_super_admin)
        self.assertFalse(self.regular_user.is_staff)
        self.assertFalse(self.regular_user.is_superuser)

    def test_cannot_demote_last_super_admin(self):
        """Ensure last super admin cannot be demoted."""
        self.client.login(username="admin", password="testpass123")

        response = self.client.get(reverse("user-demote", args=[self.super_admin.id]))
        self.assertEqual(response.status_code, 302)

        self.super_admin.refresh_from_db()
        self.assertTrue(self.super_admin.is_super_admin)

    def test_delete_super_admin_user_post_returns_forbidden(self):
        """POST to delete a super_admin user should return HTTP 403."""
        self.client.login(username="admin", password="testpass123")

        response = self.client.post(reverse("user-delete", args=[self.super_admin.id]))
        self.assertEqual(response.status_code, 403)

        # Super admin should still exist
        self.super_admin.refresh_from_db()
        self.assertTrue(self.super_admin.is_super_admin)

    def test_delete_super_admin_user_get_returns_forbidden(self):
        """GET the delete confirmation page for a super_admin should return HTTP 403."""
        self.client.login(username="admin", password="testpass123")

        response = self.client.get(reverse("user-delete", args=[self.super_admin.id]))
        self.assertEqual(response.status_code, 403)

    def test_delete_regular_user_succeeds(self):
        """POST to delete a non-super-admin approved user should succeed."""
        self.client.login(username="admin", password="testpass123")

        # Approve regular user first
        self.regular_user.profile.is_approved = True
        self.regular_user.profile.save()

        regular_user_id = self.regular_user.id
        response = self.client.post(reverse("user-delete", args=[regular_user_id]))
        self.assertEqual(response.status_code, 302)  # Redirect to success_url

        # User should be deleted
        self.assertFalse(User.objects.filter(id=regular_user_id).exists())

    def test_delete_user_requires_login(self):
        """Unauthenticated user should get 403 from SuperAdminRequiredMixin."""
        response = self.client.post(reverse("user-delete", args=[self.regular_user.id]))
        self.assertEqual(response.status_code, 403)

    def test_login_form_has_autocomplete_attribute(self):
        """Test that login form password input has autocomplete='current-password'."""
        response = self.client.get(reverse("login"))
        self.assertEqual(response.status_code, 200)

        content = response.content.decode()
        self.assertIn('autocomplete="current-password"', content)

    def test_user_create_form_has_autocomplete_attributes(self):
        """Test that user create form password inputs have autocomplete='new-password'."""
        self.client.login(username="admin", password="testpass123")

        response = self.client.get(reverse("user-create"))
        self.assertEqual(response.status_code, 200)

        content = response.content.decode()
        self.assertIn('autocomplete="new-password"', content)
        self.assertEqual(content.count('autocomplete="new-password"'), 2)

    def test_reset_password_form_has_autocomplete_attributes(self):
        """Test that password reset form inputs have autocomplete='new-password'."""
        self.client.login(username="admin", password="testpass123")

        response = self.client.get(
            reverse("user-reset-password", args=[self.regular_user.id])
        )
        self.assertEqual(response.status_code, 200)

        content = response.content.decode()
        # Both password fields should have autocomplete="new-password"
        self.assertIn('autocomplete="new-password"', content)
        # There should be exactly 2 occurrences (new_password and confirm_password)
        self.assertEqual(content.count('autocomplete="new-password"'), 2)


@override_settings(
    MIDDLEWARE=[
        "django.middleware.security.SecurityMiddleware",
        "django.contrib.sessions.middleware.SessionMiddleware",
        "django.middleware.common.CommonMiddleware",
        "django.middleware.csrf.CsrfViewMiddleware",
        "django.contrib.auth.middleware.AuthenticationMiddleware",
        "django.contrib.messages.middleware.MessageMiddleware",
        "django.middleware.clickjacking.XFrameOptionsMiddleware",
    ]
)
class SignupFormAutocompleteTests(TestCase):
    """Test that the signup form has proper autocomplete attributes."""

    def test_signup_form_has_autocomplete_attributes(self):
        """Test that signup form password inputs have autocomplete='new-password'."""
        response = self.client.get(reverse("signup"))
        self.assertEqual(response.status_code, 200)

        content = response.content.decode()
        self.assertIn('autocomplete="new-password"', content)
        self.assertEqual(content.count('autocomplete="new-password"'), 2)


@override_settings(
    MIDDLEWARE=[
        "django.middleware.security.SecurityMiddleware",
        "django.contrib.sessions.middleware.SessionMiddleware",
        "django.middleware.common.CommonMiddleware",
        "django.middleware.csrf.CsrfViewMiddleware",
        "django.contrib.auth.middleware.AuthenticationMiddleware",
        "accounts.middleware.AdminApprovalRequiredMiddleware",
        "django.contrib.messages.middleware.MessageMiddleware",
        "django.middleware.clickjacking.XFrameOptionsMiddleware",
    ]
)
class AdminApprovalMiddlewareTests(TestCase):
    """Test cases for the admin approval middleware."""

    def setUp(self):
        """Set up test data."""
        self.client = Client()
        self.super_admin = User.objects.create_user(
            username="admin", email="admin@example.com", password="testpass123"
        )
        self.unapproved_user = User.objects.create_user(
            username="unapproved",
            email="unapproved@example.com",
            password="testpass123",
        )

    def test_unapproved_user_redirected_to_login(self):
        """Test that unapproved users are redirected to login."""
        # Login as unapproved user
        self.client.login(username="unapproved", password="testpass123")

        # Try to access a protected page
        response = self.client.get(reverse("feed-list"))
        self.assertEqual(response.status_code, 302)  # Redirect to login

        # Check that user is redirected to login
        self.assertRedirects(response, reverse("login"))

    def test_super_admin_can_access_pages(self):
        """Test that super admin can access all pages."""
        self.client.login(username="admin", password="testpass123")

        # Try to access a protected page
        response = self.client.get(reverse("feed-list"))
        self.assertEqual(response.status_code, 200)  # Should be accessible

    def test_login_page_accessible_to_unapproved_users(self):
        """Test that login page is accessible to unapproved users."""
        self.client.login(username="unapproved", password="testpass123")

        # Try to access login page
        response = self.client.get(reverse("login"))
        self.assertEqual(response.status_code, 200)  # Should be accessible


class TestMigrateEnvToConfigForceParam(TestCase):
    """Test that the force parameter in migrate_env_to_config is parsed safely.

    The bug: request.POST.get("force", False) returns a string from POST data.
    Any non-empty string (including "false") is truthy in Python, so force=false
    was incorrectly treated as True.
    """

    def setUp(self):
        # First user becomes super admin (can_manage_users() returns True)
        self.admin = User.objects.create_user(
            username="admin", email="admin@example.com", password="testpass123"
        )
        self.client.login(username="admin", password="testpass123")
        self.url = reverse("migrate-env-to-config")

        # Create a GlobalConfig with an existing value that should NOT be
        # overwritten unless force is truly truthy
        self.config = GlobalConfig.get_or_create_with_env_migration()
        self.config.openai_tts_voice = "existing_voice"
        self.config.save()

    @override_settings(OPENAI_TTS_VOICE="env_voice")
    def test_force_true_overwrites_existing(self):
        """force=true should overwrite existing config values."""
        self.client.post(self.url, {"force": "true"})
        self.config.refresh_from_db()
        self.assertEqual(self.config.openai_tts_voice, "env_voice")

    @override_settings(OPENAI_TTS_VOICE="env_voice")
    def test_force_false_does_not_overwrite_existing(self):
        """force=false must NOT overwrite existing config values (the bug case)."""
        self.client.post(self.url, {"force": "false"})
        self.config.refresh_from_db()
        # AIDEV-NOTE: This is the key bug assertion — "false" string was truthy before fix
        self.assertEqual(self.config.openai_tts_voice, "existing_voice")

    @override_settings(OPENAI_TTS_VOICE="env_voice")
    def test_force_1_overwrites_existing(self):
        """force=1 should overwrite existing config values."""
        self.client.post(self.url, {"force": "1"})
        self.config.refresh_from_db()
        self.assertEqual(self.config.openai_tts_voice, "env_voice")

    @override_settings(OPENAI_TTS_VOICE="env_voice")
    def test_missing_force_does_not_overwrite_existing(self):
        """Missing force param should not overwrite existing config values."""
        self.client.post(self.url, {})
        self.config.refresh_from_db()
        self.assertEqual(self.config.openai_tts_voice, "existing_voice")

    @override_settings(OPENAI_TTS_VOICE="env_voice")
    def test_empty_force_does_not_overwrite_existing(self):
        """force= (empty string) should not overwrite existing config values."""
        self.client.post(self.url, {"force": ""})
        self.config.refresh_from_db()
        self.assertEqual(self.config.openai_tts_voice, "existing_voice")


class TestUserConfirmDeleteTemplate(TestCase):
    """Test that user_confirm_delete.html renders correctly with missing fields."""

    def setUp(self):
        # First user becomes super admin (can_manage_users() returns True)
        self.admin = User.objects.create_user(
            username="admin", email="admin@example.com", password="testpass123"
        )
        # User with no email and no name — should show "Not provided" fallback
        self.target_user = User.objects.create_user(
            username="emptyuser", email="", password="testpass123"
        )
        self.client.login(username="admin", password="testpass123")

    def test_delete_page_shows_not_provided_for_blank_fields(self):
        """Template must render 'Not provided' when email/name are blank."""
        url = reverse("user-delete", kwargs={"user_id": self.target_user.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        # AIDEV-NOTE: verifies fix for _() Python syntax used in Django template (commit 132a078)
        self.assertIn("Not provided", content)
