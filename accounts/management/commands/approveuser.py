from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Approve or revoke approval for user accounts"

    def add_arguments(self, parser):
        parser.add_argument(
            "username",
            type=str,
            help="Username of the user to approve/revoke",
        )
        parser.add_argument(
            "--revoke",
            action="store_true",
            help="Revoke approval instead of granting it",
        )
        parser.add_argument(
            "--list-pending",
            action="store_true",
            help="List all users pending approval",
        )

    def handle(self, *args, **options):
        if options.get("list_pending"):
            self.list_pending_users()
            return

        username = options["username"]
        revoke = options.get("revoke", False)

        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist:
            raise CommandError(f'User "{username}" does not exist')

        # Check if user has profile
        if not hasattr(user, "profile"):
            raise CommandError(f'User "{username}" does not have a profile')

        # Check if user is super admin
        if user.is_super_admin and revoke:
            raise CommandError("Cannot revoke approval for super admin users")

        # Perform action
        if revoke:
            if not user.is_approved:
                self.stdout.write(
                    self.style.WARNING(f'User "{username}" is already not approved')
                )
                return

            user.profile.is_approved = False
            user.profile.save()
            self.stdout.write(
                self.style.SUCCESS(
                    f'Successfully revoked approval for user "{username}"'
                )
            )
        else:
            if user.is_approved:
                self.stdout.write(
                    self.style.WARNING(f'User "{username}" is already approved')
                )
                return

            user.profile.is_approved = True
            user.profile.save()
            self.stdout.write(
                self.style.SUCCESS(f'Successfully approved user "{username}"')
            )

    def list_pending_users(self):
        """List all users pending approval."""
        pending_users = User.objects.filter(
            profile__is_approved=False, profile__is_super_admin=False
        )

        if not pending_users.exists():
            self.stdout.write(self.style.SUCCESS("No users pending approval"))
            return

        self.stdout.write(self.style.SUCCESS("Users pending approval:"))
        self.stdout.write("")

        for user in pending_users:
            email_info = f" ({user.email})" if user.email else ""
            joined_date = user.date_joined.strftime("%Y-%m-%d %H:%M")
            self.stdout.write(f"  • {user.username}{email_info} - joined {joined_date}")

        self.stdout.write("")
        self.stdout.write(f"Total: {pending_users.count()} user(s) pending approval")
        self.stdout.write("")
        self.stdout.write("To approve a user: python manage.py approveuser <username>")
        self.stdout.write(
            "To revoke approval: python manage.py approveuser <username> --revoke"
        )
