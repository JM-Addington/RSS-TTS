"""Email parsing utilities for Mailgun webhook payloads."""

import base64
import logging
from typing import Dict, List, Tuple

logger = logging.getLogger(__name__)


class EmailParser:
    """Parser for incoming email data from Mailgun webhooks."""

    @staticmethod
    def extract_text_content(email_data: Dict) -> Tuple[str, str]:
        """Extract text content from email data.

        Prioritizes plain text over HTML, but falls back to HTML if needed.

        Args:
            email_data: The email data from Mailgun webhook

        Returns:
            Tuple of (text_content, content_source) where content_source is 'plain', 'html', or 'none'

        Example:
            >>> data = {"body-plain": "Hello world", "body-html": "<p>Hello world</p>"}
            >>> text, source = EmailParser.extract_text_content(data)
            >>> print(text, source)
            Hello world plain
        """
        # Try plain text first
        plain_text = email_data.get("body-plain", "").strip()
        if plain_text:
            return plain_text, "plain"

        # Fall back to HTML
        html_text = email_data.get("body-html", "").strip()
        if html_text:
            # AIDEV-NOTE: HTML body needs to be processed to extract text
            # Reuse existing extract_article_text utility
            from text_to_audio.utils import extract_article_text

            success, extracted_text, error = extract_article_text(html_text)
            if success and extracted_text:
                return extracted_text, "html"

            # If extraction fails, return raw HTML (better than nothing)
            logger.warning(f"Failed to extract text from HTML: {error}")
            return html_text, "html"

        # No content found
        return "", "none"

    @staticmethod
    def extract_title(email_data: Dict) -> str:
        """Extract title from email subject.

        Args:
            email_data: The email data from Mailgun webhook

        Returns:
            The email subject, or a default title if subject is empty
        """
        subject = email_data.get("subject", "").strip()
        if subject:
            return subject

        # Default title if no subject
        return "Email Article"

    @staticmethod
    def extract_sender(email_data: Dict) -> str:
        """Extract sender email address.

        Args:
            email_data: The email data from Mailgun webhook

        Returns:
            The sender's email address
        """
        return email_data.get("sender", email_data.get("from", "unknown@unknown"))

    @staticmethod
    def extract_attachments(
        email_data: Dict,
    ) -> List[Dict[str, str | bytes]]:
        """Extract attachments from email data.

        Args:
            email_data: The email data from Mailgun webhook

        Returns:
            List of attachment dictionaries with keys: filename, content_type, data

        Example:
            >>> data = {"attachment-count": "1", "attachment-1": {...}}
            >>> attachments = EmailParser.extract_attachments(data)
        """
        attachments = []

        # AIDEV-NOTE: Mailgun sends attachments as multipart form data
        # - attachment-count: number of attachments
        # - attachment-1, attachment-2, etc: file objects
        # In webhook POST, these come as file uploads

        attachment_count = int(email_data.get("attachment-count", 0))

        for i in range(1, attachment_count + 1):
            attachment_key = f"attachment-{i}"
            attachment_file = email_data.get(attachment_key)

            if attachment_file:
                # attachment_file should be a file-like object or dict
                # For now, we'll handle it in the view where we have access to request.FILES
                attachments.append(
                    {
                        "key": attachment_key,
                        "filename": getattr(attachment_file, "name", f"attachment-{i}"),
                    }
                )

        return attachments

    @staticmethod
    def is_valid_email_data(email_data: Dict) -> Tuple[bool, str]:
        """Validate that email data contains required fields.

        Args:
            email_data: The email data from Mailgun webhook

        Returns:
            Tuple of (is_valid, error_message)
        """
        # Check for recipient (required to match feed)
        if not email_data.get("recipient"):
            return False, "Missing recipient field"

        # Check for some form of content
        has_content = any(
            [
                email_data.get("body-plain"),
                email_data.get("body-html"),
                int(email_data.get("attachment-count", 0)) > 0,
            ]
        )

        if not has_content:
            return False, "Email has no text content or attachments"

        return True, ""

    @staticmethod
    def extract_recipient(email_data: Dict) -> str | None:
        """Extract the recipient email address.

        Args:
            email_data: The email data from Mailgun webhook

        Returns:
            The recipient email address, or None if not found
        """
        recipient = email_data.get("recipient", "").strip()
        if not recipient:
            # Try alternative field
            recipient = email_data.get("To", "").strip()

        return recipient if recipient else None

    @staticmethod
    def parse_webhook_payload(post_data: Dict, files: Dict) -> Dict:
        """Parse the complete Mailgun webhook payload.

        Args:
            post_data: POST data from request.POST
            files: File data from request.FILES

        Returns:
            Parsed email data dictionary with all relevant fields

        Example:
            >>> parsed = EmailParser.parse_webhook_payload(request.POST, request.FILES)
            >>> print(parsed['subject'], parsed['text_content'])
        """
        # Extract basic email data
        text_content, content_source = EmailParser.extract_text_content(post_data)
        title = EmailParser.extract_title(post_data)
        sender = EmailParser.extract_sender(post_data)
        recipient = EmailParser.extract_recipient(post_data)

        # Collect attachment files
        attachment_files = []
        attachment_count = int(post_data.get("attachment-count", 0))
        for i in range(1, attachment_count + 1):
            attachment_key = f"attachment-{i}"
            if attachment_key in files:
                attachment_files.append(
                    {
                        "key": attachment_key,
                        "file": files[attachment_key],
                        "filename": files[attachment_key].name,
                        "content_type": files[attachment_key].content_type,
                    }
                )

        return {
            "subject": title,
            "text_content": text_content,
            "content_source": content_source,
            "sender": sender,
            "recipient": recipient,
            "attachments": attachment_files,
            "raw_data": dict(post_data),
        }
