from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError

from accounts.models_profile import UserProfile


class Command(BaseCommand):
    help = "Promote a user to super admin or demote from super admin"

    def add_arguments(self, parser):
        parser.add_argument(
            "username",
            type=str,
            help="Username of the user to promote/demote",
        )
        parser.add_argument(
            "--demote",
            action="store_true",
            help="Demote from super admin instead of promoting",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Force the operation even if user is already in the target state",
        )
        parser.add_argument(
            "--list-admins",
            action="store_true",
            help="List all super admin users",
        )

    def handle(self, *args, **options):
        if options.get("list_admins"):
            self.list_super_admins()
            return

        username = options["username"]
        demote = options.get("demote", False)
        force = options.get("force", False)

        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist:
            raise CommandError(f'User "{username}" does not exist')

        # Check if user has profile
        if not hasattr(user, "profile"):
            raise CommandError(f'User "{username}" does not have a profile')

        # Perform action
        if demote:
            if not user.is_super_admin and not force:
                self.stdout.write(
                    self.style.WARNING(f'User "{username}" is not a super admin')
                )
                return

            # Check if this is the only super admin
            super_admin_count = UserProfile.objects.filter(is_super_admin=True).count()
            if super_admin_count <= 1:
                raise CommandError(
                    "Cannot demote the last super admin. At least one super admin must exist."
                )

            user.profile.is_super_admin = False
            user.profile.save()
            user.is_staff = False
            user.is_superuser = False
            user.save()

            self.stdout.write(
                self.style.SUCCESS(
                    f'Successfully demoted user "{username}" from super admin'
                )
            )
            self.stdout.write(
                self.style.WARNING(
                    "Note: User approval status remains unchanged. "
                    "Use approveuser command if needed."
                )
            )
        else:
            if user.is_super_admin and not force:
                self.stdout.write(
                    self.style.WARNING(f'User "{username}" is already a super admin')
                )
                return

            user.profile.is_super_admin = True
            user.profile.is_approved = True  # Super admins must be approved
            user.profile.save()
            user.is_staff = True
            user.is_superuser = True
            user.save()

            self.stdout.write(
                self.style.SUCCESS(
                    f'Successfully promoted user "{username}" to super admin'
                )
            )
            self.stdout.write(
                self.style.SUCCESS(
                    "User has been automatically approved and granted staff access."
                )
            )

    def list_super_admins(self):
        """List all super admin users."""
        super_admins = User.objects.filter(profile__is_super_admin=True)

        if not super_admins.exists():
            self.stdout.write(self.style.ERROR("No super admin users found!"))
            self.stdout.write(
                "This should not happen. Create a super admin immediately."
            )
            return

        self.stdout.write(self.style.SUCCESS("Super admin users:"))
        self.stdout.write("")

        for user in super_admins:
            email_info = f" ({user.email})" if user.email else ""
            joined_date = user.date_joined.strftime("%Y-%m-%d %H:%M")
            approval_status = "approved" if user.is_approved else "NOT APPROVED"
            self.stdout.write(
                f"  • {user.username}{email_info} - {approval_status} - joined {joined_date}"
            )

        self.stdout.write("")
        self.stdout.write(f"Total: {super_admins.count()} super admin(s)")
        self.stdout.write("")
        self.stdout.write("To promote a user: python manage.py promoteuser <username>")
        self.stdout.write(
            "To demote a user: python manage.py promoteuser <username> --demote"
        )
