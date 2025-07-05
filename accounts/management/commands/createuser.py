import getpass

from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Create a new regular user account"

    def add_arguments(self, parser):
        parser.add_argument(
            "--username",
            type=str,
            help="Username for the new user",
        )
        parser.add_argument(
            "--email",
            type=str,
            help="Email address for the new user",
        )
        parser.add_argument(
            "--password",
            type=str,
            help="Password for the new user (will prompt if not provided)",
        )
        parser.add_argument(
            "--approved",
            action="store_true",
            help="Create user as already approved",
        )
        parser.add_argument(
            "--interactive",
            action="store_true",
            default=True,
            help="Run in interactive mode (default)",
        )
        parser.add_argument(
            "--noinput",
            action="store_false",
            dest="interactive",
            help="Do not prompt for any input",
        )

    def handle(self, *args, **options):
        username = options.get("username")
        email = options.get("email")
        password = options.get("password")
        approved = options.get("approved", False)
        interactive = options.get("interactive", True)

        username = self._get_username(username, interactive)
        email = self._get_email(email, interactive)
        password = self._get_password(password, interactive)

        self._create_user(username, email, password, approved)

    def _get_username(self, username, interactive):
        """Get and validate username."""
        if not username:
            if not interactive:
                raise CommandError("Username is required when running with --noinput")
            while not username:
                username = input("Username: ").strip()
                if not username:
                    self.stdout.write(self.style.ERROR("Username cannot be empty"))

        # Check if username already exists
        if User.objects.filter(username=username).exists():
            raise CommandError(f'User with username "{username}" already exists')

        return username

    def _get_email(self, email, interactive):
        """Get email address (optional)."""
        if not email and interactive:
            email = input("Email address (optional): ").strip()
            if not email:
                email = None
        return email

    def _get_password(self, password, interactive):
        """Get and validate password."""
        if not password:
            if not interactive:
                raise CommandError("Password is required when running with --noinput")
            password = self._prompt_for_password()

        # Validate password if provided
        if password:
            try:
                validate_password(password)
            except ValidationError as e:
                for error in e.messages:
                    raise CommandError(f"Password error: {error}")

        return password

    def _prompt_for_password(self):
        """Prompt user for password with validation."""
        password = None
        while not password:
            password = getpass.getpass("Password: ")
            if not password:
                self.stdout.write(self.style.ERROR("Password cannot be empty"))
                continue

            # Validate password
            try:
                validate_password(password)
            except ValidationError as e:
                for error in e.messages:
                    self.stdout.write(self.style.ERROR(f"Password error: {error}"))
                password = None
                continue

            # Confirm password
            password_confirm = getpass.getpass("Password (again): ")
            if password != password_confirm:
                self.stdout.write(self.style.ERROR("Passwords do not match"))
                password = None

        return password

    def _create_user(self, username, email, password, approved):
        """Create user and handle approval logic."""
        try:
            user = User.objects.create_user(
                username=username, email=email, password=password
            )

            # Set approval status via profile
            if approved and hasattr(user, "profile"):
                user.profile.is_approved = True
                user.profile.save()

            self._show_success_message(user, username)

        except Exception as e:
            raise CommandError(f"Error creating user: {e}")

    def _show_success_message(self, user, username):
        """Show appropriate success message based on user status."""
        approval_status = "approved" if user.is_approved else "pending approval"
        user_type = "super admin" if user.is_super_admin else "regular user"

        self.stdout.write(
            self.style.SUCCESS(
                f'Successfully created {user_type} "{username}" ({approval_status})'
            )
        )

        # Show additional info for first user
        if user.is_super_admin:
            self.stdout.write(
                self.style.WARNING(
                    "This is the first user and has been automatically granted super admin privileges."
                )
            )
        elif not user.is_approved:
            self.stdout.write(
                self.style.WARNING(
                    "User created but requires admin approval before they can access the system."
                )
            )
