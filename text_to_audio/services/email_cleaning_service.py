"""Service for cleaning and extracting main content from emails using LLM."""

import json
import logging
import time

from django.conf import settings

logger = logging.getLogger(__name__)

# Maximum email length to process (characters)
MAX_EMAIL_CHARS = getattr(settings, "MAX_EMAIL_CLEANING_CHARS", 50_000)


class EmailCleaningService:
    """Service for extracting main content from emails using LLM."""

    def __init__(self, openai_api_key=None):
        """Initialize with optional API key override."""
        self.openai_api_key = openai_api_key
        self._client = None

    @property
    def client(self):
        """Lazily initialize OpenAI client."""
        if self._client is None:
            import openai

            from appconfig.utils import get_openai_api_key

            self._client = openai.OpenAI(
                api_key=self.openai_api_key or get_openai_api_key()
            )
        return self._client

    def _create_cleaning_prompt(self, email_text: str, subject: str = None) -> str:
        """Create the prompt for email content extraction.

        Args:
            email_text: The raw email text
            subject: Optional email subject for context

        Returns:
            The formatted prompt
        """
        subject_context = f"\n\nEmail Subject: {subject}" if subject else ""

        prompt = f"""You are helping extract the main content from an email for audio narration.

Your task is to:
1. Extract ALL primary content that should be read aloud (including all articles/sections in newsletters)
2. Remove boilerplate elements (headers, footers, unsubscribe links, navigation, social media buttons)
3. Remove advertisements and sponsorships UNLESS they are the core subject of the email
4. Remove email signatures and metadata
5. Remove forwarding artifacts (sender's signature, "Forwarded message" headers, From/Date/Subject/To lines)
6. Preserve the narrative flow and essential information
7. Keep the content engaging and coherent for audio listening{subject_context}

Email Content:
{email_text}

Return a JSON object with:
{{
  "cleaned_content": "The extracted main content, ready for audio narration",
  "content_type": "One of: newsletter, article, personal_email, promotional, announcement, forwarded, other",
  "removed_elements": ["List of element types removed, e.g., 'footer', 'advertisement', 'forward_headers', 'user_signature'"],
  "confidence": "high/medium/low - your confidence in the extraction quality"
}}

Guidelines:
- IMPORTANT: For newsletters with multiple articles/sections, extract ALL of them, not just the first one
- If the email is ABOUT a product/service (promotional), keep the promotional content
- If the email CONTAINS ads within an article/newsletter, remove them
- For FORWARDED emails: Remove the sender's signature at the top, remove forward metadata (From:, Date:, Subject:, To:), extract only the original email body
- Remove all email signatures (both at top for forwards and at bottom for regular emails)
- Preserve important links or references that add value to the content
- Between newsletter sections, maintain clear separation (use paragraph breaks)
- Include article titles/headings within the newsletter to provide structure
- If you're uncertain whether something is core content, keep it
- Maintain natural paragraph structure for audio flow

Common forwarded email pattern to handle:
[User's signature at top]
---------- Forwarded message ---------
From: someone@example.com
Date: [date]
Subject: [subject]
To: [recipient]
[ORIGINAL EMAIL CONTENT - EXTRACT THIS]

Extract only the original email content below the forward headers.

CRITICAL: If this is a newsletter with multiple stories/articles, extract EVERY article, not just the first one. The user wants to listen to the entire newsletter."""

        return prompt

    def clean_email_content(
        self, email_text: str, subject: str = None
    ) -> tuple[bool, str, dict, str]:
        """Clean email content using LLM to extract main narrative.

        Args:
            email_text: The raw email text to clean
            subject: Optional email subject for additional context

        Returns:
            Tuple of (success, cleaned_text, metadata, error_message)
            where metadata includes: content_type, removed_elements, confidence
        """
        # AIDEV-NOTE: Truncate very long emails to avoid excessive token usage
        if len(email_text) > MAX_EMAIL_CHARS:
            logger.warning(
                f"Email text truncated from {len(email_text)} to {MAX_EMAIL_CHARS} chars"
            )
            email_text = email_text[:MAX_EMAIL_CHARS]

        # Skip cleaning if email is very short (likely already clean)
        if len(email_text.strip()) < 200:
            logger.info("Email too short for cleaning, returning as-is")
            return True, email_text, {"content_type": "short_email"}, ""

        try:
            prompt = self._create_cleaning_prompt(email_text, subject)

            # Use gpt-4o-mini for cost efficiency
            model = "gpt-4o-mini"

            request_data = {
                "model": model,
                "messages": [
                    {
                        "role": "system",
                        "content": "You are an expert at extracting main content from emails for audio narration.",
                    },
                    {"role": "user", "content": prompt},
                ],
                "max_completion_tokens": 4096,  # Generous for cleaned content
                "temperature": 0.2,  # Low temperature for consistent extraction
                "response_format": {"type": "json_object"},
            }

            logger.info(
                f"Email Cleaning API Call: model={model}, "
                f"email_length={len(email_text)} chars, "
                f"subject='{subject or 'None'}'"
            )

            start_time = time.monotonic()
            response = self.client.chat.completions.create(**request_data)
            end_time = time.monotonic()
            duration_ms = int((end_time - start_time) * 1000)

            # Extract usage data for logging
            usage_data = {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens,
            }

            logger.info(
                f"Email Cleaning API Response: duration={duration_ms}ms, "
                f"tokens={usage_data['total_tokens']} "
                f"(prompt={usage_data['prompt_tokens']}, "
                f"completion={usage_data['completion_tokens']})"
            )

            # Parse response
            content = response.choices[0].message.content
            result = json.loads(content)

            cleaned_text = result.get("cleaned_content", "")
            if not cleaned_text or not cleaned_text.strip():
                error_msg = "LLM returned empty cleaned content"
                logger.warning(error_msg)
                return False, email_text, {}, error_msg

            metadata = {
                "content_type": result.get("content_type", "unknown"),
                "removed_elements": result.get("removed_elements", []),
                "confidence": result.get("confidence", "unknown"),
                "original_length": len(email_text),
                "cleaned_length": len(cleaned_text),
                "reduction_percent": round(
                    (1 - len(cleaned_text) / len(email_text)) * 100, 1
                ),
            }

            logger.info(
                f"Email cleaning successful: {metadata['content_type']} "
                f"({metadata['confidence']} confidence), "
                f"reduced by {metadata['reduction_percent']}%"
            )

            return True, cleaned_text, metadata, ""

        except json.JSONDecodeError as e:
            error_msg = f"Failed to parse LLM JSON response: {e}"
            logger.error(error_msg)
            return False, email_text, {}, error_msg

        except Exception as e:
            error_msg = f"Email cleaning failed: {e}"
            logger.error(error_msg, exc_info=True)
            return False, email_text, {}, error_msg
