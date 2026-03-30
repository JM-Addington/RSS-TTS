"""Service for generating feed email addresses and configuring Mailgun routes."""

import logging
from dataclasses import dataclass

from django.conf import settings

from .mailgun_service import MailgunService

logger = logging.getLogger(__name__)


@dataclass
class FeedEmailResult:
    """Result of a feed email generation operation.

    Attributes:
        success: Whether the operation completed (email may be saved even on partial success)
        email: The generated or existing email address
        route_id: The Mailgun route ID if a route was created
        message: Human-readable message for the user
        level: Message level — one of "info", "warning", "error", "success"
    """

    success: bool
    email: str | None = None
    route_id: str | None = None
    message: str = ""
    level: str = "info"


# AIDEV-NOTE: FeedEmailService extracts business logic from GenerateFeedEmailView.post()
class FeedEmailService:
    """Service for generating email addresses for feeds and creating Mailgun routes.

    This service handles the business logic for email generation,
    while the view handles HTTP concerns (auth, messages, redirects).
    """

    def generate_email_for_feed(self, feed) -> FeedEmailResult:
        """Generate an inbound email address for a feed and optionally create a Mailgun route.

        Args:
            feed: A Feed instance (already validated for ownership by the caller)

        Returns:
            FeedEmailResult with the outcome of the operation
        """
        # Check if feed already has an email
        if feed.inbound_email:
            logger.info(
                f"Feed {feed.id} ({feed.name}) already has email: {feed.inbound_email}"
            )
            return FeedEmailResult(
                success=False,
                email=feed.inbound_email,
                message=f"Feed '{feed.name}' already has an email address: {feed.inbound_email}",
                level="info",
            )

        # Check if Mailgun is configured
        if not settings.MAILGUN_API_KEY or not settings.MAILGUN_DOMAIN:
            logger.error(
                f"Mailgun not configured — cannot generate email for feed {feed.id} ({feed.name})"
            )
            return FeedEmailResult(
                success=False,
                message="Mailgun is not configured. Please contact the administrator.",
                level="error",
            )

        # Generate email address
        email_address = feed.generate_inbound_email()
        if not email_address:
            logger.error(
                f"Failed to generate email address for feed {feed.id} ({feed.name})"
            )
            return FeedEmailResult(
                success=False,
                message=f"Failed to generate email address for feed '{feed.name}'.",
                level="error",
            )

        # Try to create Mailgun route if SITE_URL is configured
        site_url = getattr(settings, "SITE_URL", None)
        if not site_url:
            feed.inbound_email = email_address
            feed.save(update_fields=["inbound_email"])
            logger.warning(
                f"Created email {email_address} for feed {feed.id} ({feed.name}) "
                f"but SITE_URL not configured — route not created"
            )
            return FeedEmailResult(
                success=True,
                email=email_address,
                message=f"Created email address {email_address}, but SITE_URL is not configured. "
                f"Mailgun route must be created manually.",
                level="warning",
            )

        # Create Mailgun route
        webhook_url = f"{site_url.rstrip('/')}/api/v1/mailgun/incoming/"
        mailgun_service = MailgunService()
        success, route_id, error = mailgun_service.create_route(
            feed_email=email_address,
            webhook_url=webhook_url,
            description=f"Route for feed: {feed.name} (ID: {feed.id})",
        )

        if success and route_id:
            feed.inbound_email = email_address
            feed.mailgun_route_id = route_id
            feed.save(update_fields=["inbound_email", "mailgun_route_id"])
            logger.info(
                f"Successfully created email {email_address} and route {route_id} "
                f"for feed {feed.id} ({feed.name})"
            )
            return FeedEmailResult(
                success=True,
                email=email_address,
                route_id=route_id,
                message=f"Successfully created email address: {email_address}",
                level="success",
            )

        # Route creation failed — save email without route
        feed.inbound_email = email_address
        feed.save(update_fields=["inbound_email"])
        logger.warning(
            f"Created email {email_address} for feed {feed.id} ({feed.name}) "
            f"but failed to create Mailgun route: {error}"
        )
        return FeedEmailResult(
            success=True,
            email=email_address,
            message=f"Created email address {email_address}, but failed to create "
            f"Mailgun route. You may need to create the route manually.",
            level="warning",
        )
