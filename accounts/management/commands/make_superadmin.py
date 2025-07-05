from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Make the first user or a specified user a super admin"

    def add_arguments(self, parser):
        parser.add_argument(
            "--username",
            type=str,
            help="Username of the user to make super admin (defaults to first user)",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Force the operation even if user is already a super admin",
        )

    def handle(self, *args, **options):
        username = options.get("username")
        force = options.get("force", False)

        if username:
            try:
                user = User.objects.get(username=username)
            except User.DoesNotExist:
                raise CommandError(f'User "{username}" does not exist.')
        else:
            # Get the first user (oldest by date_joined)
            user = User.objects.order_by("date_joined").first()
            if not user:
                raise CommandError("No users found in the database.")

        # Check if user has profile
        if not hasattr(user, "profile"):
            raise CommandError(f'User "{user.username}" does not have a profile')

        if user.is_super_admin and not force:
            self.stdout.write(
                self.style.WARNING(
                    f'User "{user.username}" is already a super admin. Use --force to override.'
                )
            )
            return

        # Make the user a super admin
        user.profile.is_super_admin = True
        user.profile.is_approved = True
        user.profile.save()
        user.is_staff = True
        user.is_superuser = True
        user.save()

        self.stdout.write(
            self.style.SUCCESS(
                f'Successfully made user "{user.username}" a super admin.'
            )
        )
