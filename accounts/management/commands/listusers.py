from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.utils import timezone

from accounts.models_profile import UserProfile


class Command(BaseCommand):
    help = "List all users with their status and details"

    def add_arguments(self, parser):
        parser.add_argument(
            "--pending-only",
            action="store_true",
            help="Show only users pending approval",
        )
        parser.add_argument(
            "--admins-only",
            action="store_true",
            help="Show only super admin users",
        )
        parser.add_argument(
            "--approved-only",
            action="store_true",
            help="Show only approved users",
        )
        parser.add_argument(
            "--format",
            choices=["table", "json", "csv"],
            default="table",
            help="Output format (default: table)",
        )
        parser.add_argument(
            "--include-inactive",
            action="store_true",
            help="Include inactive users in the output",
        )

    def handle(self, *args, **options):
        # Build queryset based on filters
        queryset = User.objects.all()

        if not options.get("include_inactive"):
            queryset = queryset.filter(is_active=True)

        if options.get("pending_only"):
            queryset = queryset.filter(
                profile__is_approved=False, profile__is_super_admin=False
            )
        elif options.get("admins_only"):
            queryset = queryset.filter(profile__is_super_admin=True)
        elif options.get("approved_only"):
            queryset = queryset.filter(profile__is_approved=True)

        queryset = queryset.order_by("-date_joined")

        if not queryset.exists():
            self.stdout.write(self.style.WARNING("No users found matching criteria"))
            return

        # Output in requested format
        output_format = options.get("format", "table")

        if output_format == "table":
            self.output_table(queryset, options)
        elif output_format == "json":
            self.output_json(queryset)
        elif output_format == "csv":
            self.output_csv(queryset)

    def output_table(self, queryset, options):
        """Output users in a formatted table."""
        # Header
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("User List"))
        self.stdout.write("=" * 80)

        # Column headers
        header_format = "{:<15} {:<25} {:<12} {:<10} {:<16}"
        self.stdout.write(
            header_format.format("Username", "Email", "Status", "Type", "Joined")
        )
        self.stdout.write("-" * 80)

        # User rows
        for user in queryset:
            email = user.email or "-"
            if len(email) > 24:
                email = email[:21] + "..."

            status = self._get_status_display(user)
            user_type = "Super Admin" if user.is_super_admin else "Regular"
            joined = user.date_joined.strftime("%Y-%m-%d")

            # Color coding
            if not user.is_active:
                style = self.style.ERROR
            elif not user.is_approved and not user.is_super_admin:
                style = self.style.WARNING
            elif user.is_super_admin:
                style = self.style.SUCCESS
            else:
                style = lambda x: x  # No styling

            self.stdout.write(
                style(
                    header_format.format(
                        user.username[:14], email, status, user_type, joined
                    )
                )
            )

        # Footer
        self.stdout.write("-" * 80)
        self.stdout.write(f"Total: {queryset.count()} user(s)")

        # Summary stats
        if not any(
            [
                options.get("pending_only"),
                options.get("admins_only"),
                options.get("approved_only"),
            ]
        ):
            self._show_summary_stats()

    def output_json(self, queryset):
        """Output users in JSON format."""
        import json

        users_data = []
        for user in queryset:
            users_data.append(
                {
                    "username": user.username,
                    "email": user.email,
                    "first_name": user.first_name,
                    "last_name": user.last_name,
                    "is_active": user.is_active,
                    "is_approved": user.is_approved,
                    "is_super_admin": user.is_super_admin,
                    "date_joined": user.date_joined.isoformat(),
                    "last_login": (
                        user.last_login.isoformat() if user.last_login else None
                    ),
                }
            )

        self.stdout.write(json.dumps(users_data, indent=2))

    def output_csv(self, queryset):
        """Output users in CSV format."""
        import csv
        import sys

        writer = csv.writer(sys.stdout)

        # Header
        writer.writerow(
            [
                "username",
                "email",
                "first_name",
                "last_name",
                "is_active",
                "is_approved",
                "is_super_admin",
                "date_joined",
                "last_login",
            ]
        )

        # Data rows
        for user in queryset:
            writer.writerow(
                [
                    user.username,
                    user.email or "",
                    user.first_name or "",
                    user.last_name or "",
                    user.is_active,
                    user.is_approved,
                    user.is_super_admin,
                    user.date_joined.isoformat(),
                    user.last_login.isoformat() if user.last_login else "",
                ]
            )

    def _get_status_display(self, user):
        """Get human-readable status for a user."""
        if not user.is_active:
            return "Inactive"
        elif hasattr(user, "profile"):
            if user.profile.is_super_admin:
                return "Super Admin"
            elif user.profile.is_approved:
                return "Approved"
            else:
                return "Pending"
        else:
            return "No Profile"

    def _show_summary_stats(self):
        """Show summary statistics."""
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("Summary:"))

        total_users = User.objects.filter(is_active=True).count()
        super_admins = User.objects.filter(
            profile__is_super_admin=True, is_active=True
        ).count()
        approved_users = User.objects.filter(
            profile__is_approved=True, is_active=True, profile__is_super_admin=False
        ).count()
        pending_users = User.objects.filter(
            profile__is_approved=False, profile__is_super_admin=False, is_active=True
        ).count()
        inactive_users = User.objects.filter(is_active=False).count()

        self.stdout.write(f"  • Total active users: {total_users}")
        self.stdout.write(f"  • Super admins: {super_admins}")
        self.stdout.write(f"  • Approved regular users: {approved_users}")
        self.stdout.write(f"  • Pending approval: {pending_users}")
        if inactive_users > 0:
            self.stdout.write(f"  • Inactive users: {inactive_users}")

        if pending_users > 0:
            self.stdout.write("")
            self.stdout.write(
                self.style.WARNING(f"{pending_users} user(s) need approval!")
            )
            self.stdout.write("Run: python manage.py approveuser --list-pending")
