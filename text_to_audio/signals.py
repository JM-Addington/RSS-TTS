"""Signal handlers for Feed model to manage Mailgun routes."""

import logging

from django.conf import settings
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from .models import Feed
from .services.mailgun_service import MailgunService

logger = logging.getLogger(__name__)


@receiver(post_save, sender=Feed)
def create_feed_email_and_route(sender, instance, created, **kwargs):
    """Automatically create email address and Mailgun route for new feeds.

    Args:
        sender: The Feed model class
        instance: The Feed instance being saved
        created: Boolean indicating if this is a new instance
        **kwargs: Additional keyword arguments
    """
    # Only process newly created feeds
    if not created:
        return

    # Check if Mailgun is configured
    if not settings.MAILGUN_API_KEY or not settings.MAILGUN_DOMAIN:
        logger.info(
            f"Mailgun not configured, skipping email generation for feed {instance.pk}"
        )
        return

    # Generate email address
    email_address = instance.generate_inbound_email()
    if not email_address:
        logger.warning(f"Failed to generate email address for feed {instance.pk}")
        return

    # AIDEV-NOTE: Generate webhook URL from SITE_URL or build from request context
    # In signal context, we don't have request, so use SITE_URL setting
    site_url = getattr(settings, "SITE_URL", None)
    if not site_url:
        logger.warning(
            "SITE_URL not configured, cannot create Mailgun route. "
            "Please set SITE_URL in your environment variables."
        )
        # Still save the email address for manual route creation
        instance.inbound_email = email_address
        instance.save(update_fields=["inbound_email"])
        return

    # Build webhook URL
    webhook_url = f"{site_url.rstrip('/')}/api/v1/mailgun/incoming/"

    # Create Mailgun route
    mailgun_service = MailgunService()
    success, route_id, error = mailgun_service.create_route(
        feed_email=email_address,
        webhook_url=webhook_url,
        description=f"Route for feed: {instance.name} (ID: {instance.pk})",
    )

    if success and route_id:
        # Save email and route ID to feed
        instance.inbound_email = email_address
        instance.mailgun_route_id = route_id
        instance.save(update_fields=["inbound_email", "mailgun_route_id"])
        logger.info(
            f"Created email {email_address} and route {route_id} for feed {instance.pk}"
        )
    else:
        # Save just the email address even if route creation failed
        instance.inbound_email = email_address
        instance.save(update_fields=["inbound_email"])
        logger.error(
            f"Failed to create Mailgun route for feed {instance.pk}: {error}. "
            f"Email address saved, but route must be created manually."
        )


@receiver(post_delete, sender=Feed)
def delete_feed_mailgun_route(sender, instance, **kwargs):
    """Clean up Mailgun route when a feed is deleted.

    Args:
        sender: The Feed model class
        instance: The Feed instance being deleted
        **kwargs: Additional keyword arguments
    """
    # Only process if feed has a route ID
    if not instance.mailgun_route_id:
        return

    # Check if Mailgun is configured
    if not settings.MAILGUN_API_KEY:
        logger.warning(
            f"Mailgun not configured, cannot delete route {instance.mailgun_route_id}"
        )
        return

    # Delete the route
    mailgun_service = MailgunService()
    success, error = mailgun_service.delete_route(instance.mailgun_route_id)

    if success:
        logger.info(
            f"Deleted Mailgun route {instance.mailgun_route_id} for feed {instance.pk}"
        )
    else:
        logger.error(
            f"Failed to delete Mailgun route {instance.mailgun_route_id} "
            f"for feed {instance.pk}: {error}"
        )
