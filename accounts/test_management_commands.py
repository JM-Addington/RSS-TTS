from django.test import TestCase
from django.contrib.auth.models import User
from django.core.management import call_command, CommandError
from django.test.utils import override_settings
from io import StringIO
import json


class ManagementCommandTests(TestCase):
    """Test cases for custom management commands."""

    def setUp(self):
        """Set up test data."""
        # Clear any existing users
        User.objects.all().delete()

    def test_createuser_interactive_mode(self):
        """Test createuser command with provided arguments."""
        # Test creating a user with all arguments
        call_command(
            'createuser',
            '--username=testuser',
            '--email=test@example.com',
            '--password=complexpass123',
            '--noinput'
        )

        user = User.objects.get(username='testuser')
        self.assertEqual(user.email, 'test@example.com')
        self.assertTrue(user.is_super_admin)  # First user becomes super admin
        self.assertTrue(user.is_approved)

    def test_createuser_second_user_not_approved(self):
        """Test that second user is not auto-approved."""
        # Create first user
        User.objects.create_user(
            username='firstuser',
            password='testpass123'
        )

        # Create second user
        call_command(
            'createuser',
            '--username=seconduser',
            '--password=complexpass123',
            '--noinput'
        )

        second_user = User.objects.get(username='seconduser')
        self.assertFalse(second_user.is_super_admin)
        self.assertFalse(second_user.is_approved)

    def test_createuser_with_approved_flag(self):
        """Test creating user with --approved flag."""
        # Create first user
        User.objects.create_user(username='firstuser', password='testpass123')

        # Create second user with approval
        call_command(
            'createuser',
            '--username=approveduser',
            '--password=complexpass123',
            '--approved',
            '--noinput'
        )

        user = User.objects.get(username='approveduser')
        self.assertTrue(user.is_approved)
        self.assertFalse(user.is_super_admin)

    def test_createuser_duplicate_username(self):
        """Test error handling for duplicate usernames."""
        User.objects.create_user(username='existing', password='testpass123')

        with self.assertRaises(CommandError) as context:
            call_command(
                'createuser',
                '--username=existing',
                '--password=complexpass123',
                '--noinput'
            )

        self.assertIn('already exists', str(context.exception))

    def test_approveuser_approve_user(self):
        """Test approving a user."""
        user = User.objects.create_user(
            username='pendinguser',
            password='testpass123'
        )
        # Create first user so this one isn't auto-approved
        User.objects.create_user(username='firstuser', password='testpass123')
        user.profile.is_approved = False
        user.profile.save()

        call_command('approveuser', 'pendinguser')

        user.refresh_from_db()
        self.assertTrue(user.is_approved)

    def test_approveuser_revoke_approval(self):
        """Test revoking user approval."""
        # Create first user (super admin)
        super_admin = User.objects.create_user(
            username='admin',
            password='testpass123'
        )

        # Create regular user
        user = User.objects.create_user(
            username='regularuser',
            password='testpass123'
        )
        user.profile.is_approved = True
        user.profile.save()

        call_command('approveuser', 'regularuser', '--revoke')

        user.refresh_from_db()
        self.assertFalse(user.is_approved)

    def test_approveuser_cannot_revoke_super_admin(self):
        """Test that super admin approval cannot be revoked."""
        super_admin = User.objects.create_user(
            username='admin',
            password='testpass123'
        )

        with self.assertRaises(CommandError) as context:
            call_command('approveuser', 'admin', '--revoke')

        self.assertIn('Cannot revoke approval for super admin', str(context.exception))

    def test_approveuser_list_pending(self):
        """Test listing pending users."""
        # Create super admin
        User.objects.create_user(username='admin', password='testpass123')

        # Create pending users
        User.objects.create_user(username='pending1', password='testpass123')
        User.objects.create_user(username='pending2', password='testpass123')

        out = StringIO()
        call_command('approveuser', 'dummy', '--list-pending', stdout=out)

        output = out.getvalue()
        self.assertIn('pending1', output)
        self.assertIn('pending2', output)

    def test_promoteuser_promote_to_super_admin(self):
        """Test promoting a user to super admin."""
        # Create first user (auto super admin)
        User.objects.create_user(username='admin', password='testpass123')

        # Create regular user
        user = User.objects.create_user(
            username='regularuser',
            password='testpass123'
        )

        call_command('promoteuser', 'regularuser')

        user.refresh_from_db()
        self.assertTrue(user.is_super_admin)
        self.assertTrue(user.is_approved)
        self.assertTrue(user.is_staff)
        self.assertTrue(user.is_superuser)

    def test_promoteuser_demote_from_super_admin(self):
        """Test demoting a user from super admin."""
        # Create two super admins
        admin1 = User.objects.create_user(username='admin1', password='testpass123')
        admin2 = User.objects.create_user(username='admin2', password='testpass123')
        admin2.profile.is_super_admin = True
        admin2.profile.save()
        admin2.is_staff = True
        admin2.is_superuser = True
        admin2.save()

        call_command('promoteuser', 'admin2', '--demote')

        admin2.refresh_from_db()
        self.assertFalse(admin2.is_super_admin)
        self.assertFalse(admin2.is_staff)
        self.assertFalse(admin2.is_superuser)

    def test_promoteuser_cannot_demote_last_super_admin(self):
        """Test that the last super admin cannot be demoted."""
        admin = User.objects.create_user(username='admin', password='testpass123')

        with self.assertRaises(CommandError) as context:
            call_command('promoteuser', 'admin', '--demote')

        self.assertIn('Cannot demote the last super admin', str(context.exception))

    def test_promoteuser_list_admins(self):
        """Test listing super admin users."""
        # Create super admin
        admin = User.objects.create_user(username='admin', password='testpass123')

        out = StringIO()
        call_command('promoteuser', 'dummy', '--list-admins', stdout=out)

        output = out.getvalue()
        self.assertIn('admin', output)
        self.assertIn('Super admin users:', output)

    def test_listusers_table_format(self):
        """Test listing users in table format."""
        # Create test users
        admin = User.objects.create_user(username='admin', password='testpass123')
        regular = User.objects.create_user(username='regular', password='testpass123')
        regular.profile.is_approved = True
        regular.profile.save()

        out = StringIO()
        call_command('listusers', stdout=out)

        output = out.getvalue()
        self.assertIn('admin', output)
        self.assertIn('regular', output)
        self.assertIn('Super Admin', output)
        self.assertIn('Regular', output)

    def test_listusers_pending_only(self):
        """Test listing only pending users."""
        # Create super admin
        User.objects.create_user(username='admin', password='testpass123')

        # Create pending user
        User.objects.create_user(username='pending', password='testpass123')

        out = StringIO()
        call_command('listusers', '--pending-only', stdout=out)

        output = out.getvalue()
        self.assertIn('pending', output)
        self.assertNotIn('admin', output)

    def test_listusers_json_format(self):
        """Test listing users in JSON format."""
        admin = User.objects.create_user(
            username='admin',
            email='admin@example.com',
            password='testpass123'
        )

        out = StringIO()
        call_command('listusers', '--format=json', stdout=out)

        output = out.getvalue()
        data = json.loads(output)

        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]['username'], 'admin')
        self.assertEqual(data[0]['email'], 'admin@example.com')
        self.assertTrue(data[0]['is_super_admin'])

    def test_make_superadmin_command(self):
        """Test the make_superadmin command."""
        user = User.objects.create_user(username='regular', password='testpass123')
        # Create first user so this one isn't auto super admin
        User.objects.create_user(username='firstuser', password='testpass123')
        user.profile.is_super_admin = False
        user.profile.is_approved = False
        user.profile.save()

        call_command('make_superadmin', '--username=regular')

        user.refresh_from_db()
        self.assertTrue(user.is_super_admin)
        self.assertTrue(user.is_approved)
        self.assertTrue(user.is_staff)
        self.assertTrue(user.is_superuser)

    def test_make_superadmin_first_user(self):
        """Test make_superadmin with first user logic."""
        # Create two users
        user1 = User.objects.create_user(username='user1', password='testpass123')
        User.objects.create_user(username='user2', password='testpass123')

        # Make the first user (by date_joined) a super admin
        call_command('make_superadmin')  # No username specified

        user1.refresh_from_db()
        self.assertTrue(user1.is_super_admin)
