"""Management command to generate email addresses for feeds without them."""

from django.conf import settings
from django.core.management.base import BaseCommand

from text_to_audio.models import Feed
from text_to_audio.services.mailgun_service import MailgunService


class Command(BaseCommand):
    """Generate inbound email addresses for feeds that don't have them."""

    help = "Generate email addresses and Mailgun routes for existing feeds"

    def add_arguments(self, parser):
        """Add command arguments."""
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be done without making changes",
        )
        parser.add_argument(
            "--skip-routes",
            action="store_true",
            help="Only generate email addresses, don't create Mailgun routes",
        )

    def handle(self, *args, **options):
        """Execute the command."""
        dry_run = options["dry_run"]
        skip_routes = options["skip_routes"]

        # Check if Mailgun is configured
        if not settings.MAILGUN_API_KEY or not settings.MAILGUN_DOMAIN:
            self.stdout.write(
                self.style.ERROR(
                    "Mailgun is not configured. Please set MAILGUN_API_KEY and "
                    "MAILGUN_DOMAIN in your environment."
                )
            )
            return

        # Get feeds without email addresses
        feeds_without_email = Feed.objects.filter(inbound_email__isnull=True)
        total_feeds = feeds_without_email.count()

        if total_feeds == 0:
            self.stdout.write(
                self.style.SUCCESS("All feeds already have email addresses!")
            )
            return

        self.stdout.write(f"Found {total_feeds} feeds without email addresses")

        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN - No changes will be made"))

        # Check if SITE_URL is configured (needed for routes)
        site_url = getattr(settings, "SITE_URL", None)
        if not skip_routes and not site_url:
            self.stdout.write(
                self.style.WARNING(
                    "SITE_URL not configured. Will only generate email addresses "
                    "without creating Mailgun routes. Set SITE_URL to create routes."
                )
            )
            skip_routes = True

        success_count = 0
        route_count = 0
        error_count = 0

        for feed in feeds_without_email:
            # Generate email address
            email_address = feed.generate_inbound_email()
            if not email_address:
                self.stdout.write(
                    self.style.ERROR(
                        f"Failed to generate email for feed {feed.id} ({feed.name})"
                    )
                )
                error_count += 1
                continue

            if dry_run:
                self.stdout.write(
                    f"Would generate: {email_address} for feed {feed.id} ({feed.name})"
                )
                success_count += 1
                continue

            # Save email address
            feed.inbound_email = email_address

            # Create Mailgun route if requested
            route_id = None
            if not skip_routes:
                webhook_url = f"{site_url.rstrip('/')}/api/v1/mailgun/incoming/"
                mailgun_service = MailgunService()
                success, route_id, error = mailgun_service.create_route(
                    feed_email=email_address,
                    webhook_url=webhook_url,
                    description=f"Route for feed: {feed.name} (ID: {feed.id})",
                )

                if success and route_id:
                    feed.mailgun_route_id = route_id
                    route_count += 1
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"Created email {email_address} and route {route_id} "
                            f"for feed {feed.id} ({feed.name})"
                        )
                    )
                else:
                    self.stdout.write(
                        self.style.WARNING(
                            f"Created email {email_address} for feed {feed.id} "
                            f"({feed.name}) but failed to create route: {error}"
                        )
                    )
            else:
                self.stdout.write(
                    self.style.SUCCESS(
                        f"Generated email {email_address} for feed {feed.id} "
                        f"({feed.name})"
                    )
                )

            # Save the feed
            feed.save(update_fields=["inbound_email", "mailgun_route_id"])
            success_count += 1

        # Summary
        self.stdout.write("\n" + "=" * 60)
        if dry_run:
            self.stdout.write(
                self.style.SUCCESS(f"DRY RUN: Would process {success_count} feeds")
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Successfully generated {success_count} email addresses"
                )
            )
            if not skip_routes:
                self.stdout.write(
                    self.style.SUCCESS(f"Created {route_count} Mailgun routes")
                )
            if error_count > 0:
                self.stdout.write(
                    self.style.ERROR(f"Failed to process {error_count} feeds")
                )
