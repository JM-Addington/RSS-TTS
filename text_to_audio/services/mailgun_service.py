"""Service for managing Mailgun routes and email ingestion."""

import hashlib
import hmac
import logging
from typing import Dict, Tuple

import requests
from django.conf import settings

logger = logging.getLogger(__name__)


class MailgunService:
    """Service for interacting with the Mailgun API."""

    def __init__(self):
        """Initialize the Mailgun service with configuration from settings."""
        self.api_key = settings.MAILGUN_API_KEY
        self.domain = settings.MAILGUN_DOMAIN
        self.webhook_signing_key = settings.MAILGUN_WEBHOOK_SIGNING_KEY
        self.base_url = "https://api.mailgun.net/v3"

    def _is_configured(self) -> bool:
        """Check if Mailgun is properly configured.

        Returns:
            True if API key and domain are set, False otherwise
        """
        return bool(self.api_key and self.domain)

    def create_route(
        self, feed_email: str, webhook_url: str, description: str = ""
    ) -> Tuple[bool, str | None, str | None]:
        """Create a Mailgun route for incoming emails.

        Args:
            feed_email: The email address to match (e.g., "happy-river-42@mg.example.com")
            webhook_url: The URL to forward emails to
            description: Optional description for the route

        Returns:
            Tuple of (success, route_id, error_message)

        Example:
            >>> service = MailgunService()
            >>> success, route_id, error = service.create_route(
            ...     "happy-river-42@mg.example.com",
            ...     "https://example.com/api/v1/mailgun/incoming/"
            ... )
        """
        if not self._is_configured():
            return False, None, "Mailgun is not configured (missing API key or domain)"

        try:
            # AIDEV-NOTE: Routes use match_recipient expression to filter incoming emails
            # Priority 0 = highest priority (processed first)
            # forward() action sends email data to webhook URL
            # stop() prevents further route processing
            response = requests.post(
                f"{self.base_url}/routes",
                auth=("api", self.api_key),
                data={
                    "priority": 0,
                    "description": description or f"Route for {feed_email}",
                    "expression": f"match_recipient('{feed_email}')",
                    "action": [f"forward('{webhook_url}')", "stop()"],
                },
                timeout=10,
            )

            response.raise_for_status()
            data = response.json()

            # Extract route ID from response
            route_id = data.get("route", {}).get("id")
            if not route_id:
                return False, None, "Route created but no ID returned"

            logger.info(f"Created Mailgun route {route_id} for {feed_email}")
            return True, route_id, None

        except requests.exceptions.HTTPError as e:
            error_msg = f"HTTP error creating route: {e}"
            if e.response is not None:
                error_msg += f" - {e.response.text}"
            logger.error(error_msg)
            return False, None, error_msg

        except requests.exceptions.RequestException as e:
            error_msg = f"Network error creating route: {e}"
            logger.error(error_msg)
            return False, None, error_msg

        except Exception as e:
            error_msg = f"Unexpected error creating route: {e}"
            logger.error(error_msg)
            return False, None, error_msg

    def delete_route(self, route_id: str) -> Tuple[bool, str | None]:
        """Delete a Mailgun route.

        Args:
            route_id: The ID of the route to delete

        Returns:
            Tuple of (success, error_message)
        """
        if not self._is_configured():
            return False, "Mailgun is not configured (missing API key or domain)"

        if not route_id:
            return False, "No route ID provided"

        try:
            response = requests.delete(
                f"{self.base_url}/routes/{route_id}",
                auth=("api", self.api_key),
                timeout=10,
            )

            response.raise_for_status()
            logger.info(f"Deleted Mailgun route {route_id}")
            return True, None

        except requests.exceptions.HTTPError as e:
            error_msg = f"HTTP error deleting route: {e}"
            if e.response is not None:
                error_msg += f" - {e.response.text}"
            logger.error(error_msg)
            return False, error_msg

        except requests.exceptions.RequestException as e:
            error_msg = f"Network error deleting route: {e}"
            logger.error(error_msg)
            return False, error_msg

        except Exception as e:
            error_msg = f"Unexpected error deleting route: {e}"
            logger.error(error_msg)
            return False, error_msg

    def verify_webhook_signature(
        self, timestamp: str, token: str, signature: str
    ) -> bool:
        """Verify that a webhook request came from Mailgun.

        Args:
            timestamp: Timestamp from webhook request
            token: Token from webhook request
            signature: Signature from webhook request

        Returns:
            True if signature is valid, False otherwise

        Example:
            >>> service = MailgunService()
            >>> is_valid = service.verify_webhook_signature(
            ...     timestamp="1234567890",
            ...     token="abc123",
            ...     signature="def456"
            ... )
        """
        if not self.webhook_signing_key:
            logger.warning(
                "Webhook signing key not configured, cannot verify signature"
            )
            return False

        # AIDEV-NOTE: Mailgun webhook signature verification
        # Compute HMAC SHA256 of timestamp + token using signing key
        # Compare with provided signature to prevent spoofing
        hmac_digest = hmac.new(
            key=self.webhook_signing_key.encode(),
            msg=f"{timestamp}{token}".encode(),
            digestmod=hashlib.sha256,
        ).hexdigest()

        return hmac.compare_digest(hmac_digest, signature)

    def get_route(self, route_id: str) -> Tuple[bool, Dict | None, str | None]:
        """Get details of a specific route.

        Args:
            route_id: The ID of the route to retrieve

        Returns:
            Tuple of (success, route_data, error_message)
        """
        if not self._is_configured():
            return False, None, "Mailgun is not configured (missing API key or domain)"

        try:
            response = requests.get(
                f"{self.base_url}/routes/{route_id}",
                auth=("api", self.api_key),
                timeout=10,
            )

            response.raise_for_status()
            data = response.json()
            return True, data.get("route"), None

        except requests.exceptions.HTTPError as e:
            error_msg = f"HTTP error getting route: {e}"
            if e.response is not None:
                error_msg += f" - {e.response.text}"
            logger.error(error_msg)
            return False, None, error_msg

        except requests.exceptions.RequestException as e:
            error_msg = f"Network error getting route: {e}"
            logger.error(error_msg)
            return False, None, error_msg

        except Exception as e:
            error_msg = f"Unexpected error getting route: {e}"
            logger.error(error_msg)
            return False, None, error_msg
