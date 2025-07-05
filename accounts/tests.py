from django.test import TestCase, Client, override_settings
from django.contrib.auth.models import User
from django.urls import reverse
from django.contrib.messages import get_messages
from accounts.models_profile import UserProfile


class UserProfileTests(TestCase):
    """Test cases for the UserProfile model."""

    def test_first_user_becomes_super_admin(self):
        """Test that the first user created becomes a super admin."""
        user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )

        self.assertTrue(user.is_super_admin)
        self.assertTrue(user.is_approved)
        self.assertTrue(user.is_staff)
        self.assertTrue(user.is_superuser)

    def test_second_user_is_not_auto_approved(self):
        """Test that subsequent users are not auto-approved."""
        # Create first user
        User.objects.create_user(
            username='firstuser',
            email='first@example.com',
            password='testpass123'
        )

        # Create second user
        second_user = User.objects.create_user(
            username='seconduser',
            email='second@example.com',
            password='testpass123'
        )

        self.assertFalse(second_user.is_super_admin)
        self.assertFalse(second_user.is_approved)
        self.assertFalse(second_user.is_staff)
        self.assertFalse(second_user.is_superuser)

    def test_can_manage_users_method(self):
        """Test the can_manage_users method."""
        # Create super admin
        super_admin = User.objects.create_user(
            username='superadmin',
            email='admin@example.com',
            password='testpass123'
        )

        # Create regular user
        regular_user = User.objects.create_user(
            username='regular',
            email='regular@example.com',
            password='testpass123'
        )

        self.assertTrue(super_admin.can_manage_users())
        self.assertFalse(regular_user.can_manage_users())


@override_settings(MIDDLEWARE=[
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
])
class UserManagementViewTests(TestCase):
    """Test cases for user management views."""

    def setUp(self):
        """Set up test data."""
        self.client = Client()
        self.super_admin = User.objects.create_user(
            username='admin',
            email='admin@example.com',
            password='testpass123'
        )
        self.regular_user = User.objects.create_user(
            username='regular',
            email='regular@example.com',
            password='testpass123'
        )

    def test_user_management_requires_super_admin(self):
        """Test that user management requires super admin privileges."""
        # Test unauthenticated access
        response = self.client.get(reverse('user-management'))
        self.assertEqual(response.status_code, 403)

        # Test regular user access
        self.client.login(username='regular', password='testpass123')
        response = self.client.get(reverse('user-management'))
        self.assertEqual(response.status_code, 403)

        # Test super admin access
        self.client.login(username='admin', password='testpass123')
        response = self.client.get(reverse('user-management'))
        self.assertEqual(response.status_code, 200)

    def test_user_approval_function(self):
        """Test user approval functionality."""
        self.client.login(username='admin', password='testpass123')

        # Regular user should not be approved initially
        self.assertFalse(self.regular_user.is_approved)

        # Approve the user
        response = self.client.get(reverse('user-approve', args=[self.regular_user.id]))
        self.assertEqual(response.status_code, 302)  # Redirect after approval

        # Check that user is now approved
        self.regular_user.refresh_from_db()
        self.assertTrue(self.regular_user.is_approved)

    def test_user_approval_revocation(self):
        """Test revoking user approval."""
        self.client.login(username='admin', password='testpass123')

        # First approve the user
        self.regular_user.profile.is_approved = True
        self.regular_user.profile.save()

        # Revoke approval
        response = self.client.get(reverse('user-revoke-approval', args=[self.regular_user.id]))
        self.assertEqual(response.status_code, 302)  # Redirect after revocation

        # Check that user approval is revoked
        self.regular_user.refresh_from_db()
        self.assertFalse(self.regular_user.is_approved)

    def test_cannot_revoke_super_admin_approval(self):
        """Test that super admin approval cannot be revoked."""
        self.client.login(username='admin', password='testpass123')

        # Try to revoke super admin approval
        response = self.client.get(reverse('user-revoke-approval', args=[self.super_admin.id]))
        self.assertEqual(response.status_code, 302)  # Redirect

        # Check that super admin is still approved
        self.super_admin.refresh_from_db()
        self.assertTrue(self.super_admin.is_approved)

    def test_user_creation_by_admin(self):
        """Test that super admin can create new users."""
        self.client.login(username='admin', password='testpass123')

        response = self.client.post(reverse('user-create'), {
            'username': 'newuser',
            'password1': 'complexpass123',
            'password2': 'complexpass123',
        })

        self.assertEqual(response.status_code, 302)  # Redirect after creation

        # Check that user was created
        new_user = User.objects.get(username='newuser')
        self.assertFalse(new_user.is_super_admin)
        self.assertFalse(new_user.is_approved)


@override_settings(MIDDLEWARE=[
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'accounts.middleware.AdminApprovalRequiredMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
])
class AdminApprovalMiddlewareTests(TestCase):
    """Test cases for the admin approval middleware."""

    def setUp(self):
        """Set up test data."""
        self.client = Client()
        self.super_admin = User.objects.create_user(
            username='admin',
            email='admin@example.com',
            password='testpass123'
        )
        self.unapproved_user = User.objects.create_user(
            username='unapproved',
            email='unapproved@example.com',
            password='testpass123'
        )

    def test_unapproved_user_redirected_to_login(self):
        """Test that unapproved users are redirected to login."""
        # Login as unapproved user
        self.client.login(username='unapproved', password='testpass123')

        # Try to access a protected page
        response = self.client.get(reverse('feed-list'))
        self.assertEqual(response.status_code, 302)  # Redirect to login

        # Check that user is redirected to login
        self.assertRedirects(response, reverse('login'))

    def test_super_admin_can_access_pages(self):
        """Test that super admin can access all pages."""
        self.client.login(username='admin', password='testpass123')

        # Try to access a protected page
        response = self.client.get(reverse('feed-list'))
        self.assertEqual(response.status_code, 200)  # Should be accessible

    def test_login_page_accessible_to_unapproved_users(self):
        """Test that login page is accessible to unapproved users."""
        self.client.login(username='unapproved', password='testpass123')

        # Try to access login page
        response = self.client.get(reverse('login'))
        self.assertEqual(response.status_code, 200)  # Should be accessible
