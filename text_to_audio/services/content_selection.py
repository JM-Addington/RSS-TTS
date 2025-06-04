"""Service for intelligent content selection from web pages using GPT-4.1."""

import json
import logging
import time
from typing import Optional, Tuple

from django.conf import settings

logger = logging.getLogger(__name__)

# Maximum HTML length to send to GPT for analysis
# Approximately 50k characters - conservative limit to avoid context issues
MAX_HTML_ANALYSIS_LENGTH = getattr(settings, "MAX_HTML_ANALYSIS_LENGTH", 50_000)

# Maximum completion token limit for content selection
# Conservative limit since we mainly need extracted text, not complex analysis
MAX_COMPLETION_TOKENS = 8_000

# Rough approximation: 1 token ≈ 4 characters
CHARS_PER_TOKEN = 4


class ContentSelectionService:
    """Service for intelligent content selection from HTML using GPT-4.1."""

    def __init__(self, openai_api_key=None, usage_logger=None):
        """Initialize with optional API key override and usage logger."""
        self.openai_api_key = openai_api_key
        self._client = None
        self.usage_logger = usage_logger

    @property
    def client(self):
        """Lazily initialize OpenAI client."""
        if self._client is None:
            from django.conf import settings

            import openai

            self._client = openai.OpenAI(
                api_key=self.openai_api_key or settings.OPENAI_API_KEY
            )
        return self._client

    def _estimate_token_count(self, text: str) -> int:
        """Estimate token count for text using simple approximation."""
        return len(text) // CHARS_PER_TOKEN

    def _truncate_html_if_needed(self, html: str, url: str) -> str:
        """Truncate HTML if it exceeds the maximum analysis length."""
        if len(html) <= MAX_HTML_ANALYSIS_LENGTH:
            return html

        # Truncate to max length and try to find a reasonable breaking point
        truncated = html[:MAX_HTML_ANALYSIS_LENGTH]

        # Try to break at a tag boundary to avoid malformed HTML
        last_tag_end = truncated.rfind(">")
        if (
            last_tag_end > MAX_HTML_ANALYSIS_LENGTH * 0.8
        ):  # If we can find a good breaking point
            truncated = truncated[: last_tag_end + 1]

        logger.warning(
            f"HTML for {url} truncated from {len(html)} to {len(truncated)} characters "
            f"for GPT analysis"
        )

        return truncated

    def extract_content_with_gpt(
        self, html: str, url: str
    ) -> Tuple[bool, str, Optional[str]]:
        """
        Extract clean article content from HTML using GPT-4.1.

        Args:
            html: Raw HTML content from the webpage
            url: Source URL for context and logging

        Returns:
            Tuple of (success, extracted_text, error_message).
            If successful, error_message will be None.
        """
        try:
            # Truncate HTML if needed to stay within token limits
            analysis_html = self._truncate_html_if_needed(html, url)

            # Create the content selection prompt
            prompt = self._create_content_selection_prompt(analysis_html, url)

            # Get the model to use
            model = self._get_content_selection_model()

            # Estimate tokens and ensure we stay within limits
            estimated_prompt_tokens = self._estimate_token_count(prompt)
            if estimated_prompt_tokens > 40_000:  # Conservative limit for prompt
                logger.warning(
                    f"Prompt for {url} estimated at {estimated_prompt_tokens} tokens, "
                    f"may hit context limits"
                )

            # Prepare request data
            request_data = {
                "model": model,
                "messages": [
                    {
                        "role": "system",
                        "content": "You are an expert content extraction assistant. Your job is to identify and extract only the main article content from HTML, removing all navigation, ads, comments, and other non-essential content.",
                    },
                    {"role": "user", "content": prompt},
                ],
                "max_tokens": MAX_COMPLETION_TOKENS,
                "temperature": 0.1,  # Low temperature for consistent extraction
                "response_format": {"type": "json_object"},
            }

            # Log content selection API call details
            logger.info(
                f"Content Selection API Call: model={model}, "
                f"max_tokens={MAX_COMPLETION_TOKENS}, temperature=0.1, "
                f"prompt_length={len(prompt)} chars, "
                f"html_length={len(analysis_html)} chars, "
                f"url='{url}'"
            )

            # Call OpenAI API
            start_time = time.monotonic()
            try:
                response = self.client.chat.completions.create(**request_data)
                end_time = time.monotonic()
                duration_ms = int((end_time - start_time) * 1000)

                # Extract response data for logging
                response_data = {
                    "id": response.id,
                    "model": response.model,
                    "usage": (
                        {
                            "prompt_tokens": response.usage.prompt_tokens,
                            "completion_tokens": response.usage.completion_tokens,
                            "total_tokens": response.usage.total_tokens,
                        }
                        if response.usage
                        else None
                    ),
                }

                # Log successful API call
                from ..utils import log_openai_api_call

                log_openai_api_call(
                    operation="Content Selection",
                    request_data=request_data,
                    response_data=response_data,
                    duration_ms=duration_ms,
                )

                # Log usage statistics if usage logger is available
                if self.usage_logger and response.usage:
                    self.usage_logger.log_llm_usage(
                        operation="Content Selection",
                        tokens_used=response.usage.total_tokens,
                        processing_time_ms=duration_ms,
                        word_count=len(analysis_html.split()),
                        model_name=model,
                        input_tokens=response.usage.prompt_tokens,
                        output_tokens=response.usage.completion_tokens,
                    )

            except Exception as e:
                end_time = time.monotonic()
                duration_ms = int((end_time - start_time) * 1000)

                # Log failed API call
                from ..utils import log_openai_api_call

                log_openai_api_call(
                    operation="Content Selection",
                    request_data=request_data,
                    error=e,
                    duration_ms=duration_ms,
                )
                raise

            # Parse the response
            try:
                content = response.choices[0].message.content
                result = json.loads(content)

                # Validate the response structure
                if "extracted_content" not in result:
                    raise ValueError("Missing 'extracted_content' in GPT response.")

                extracted_text = result["extracted_content"]
                if not isinstance(extracted_text, str):
                    raise ValueError("'extracted_content' must be a string.")

                if not extracted_text.strip():
                    raise ValueError("Extracted content is empty.")

                # Log extraction success
                logger.info(
                    f"Successfully extracted {len(extracted_text)} characters "
                    f"from {len(html)} character HTML for {url}"
                )

                return True, extracted_text.strip(), None

            except (json.JSONDecodeError, ValueError, KeyError, IndexError) as e:
                logger.error(f"Error parsing content selection response for {url}: {e}")
                logger.error(f"GPT Response Content: {content}")
                return False, "", f"Failed to parse GPT response: {e}"

        except Exception as e:
            error_message = f"Error in GPT content selection for {url}: {str(e)}"
            logger.error(error_message)
            return False, "", error_message

    def _create_content_selection_prompt(self, html: str, url: str) -> str:
        """Create the prompt for intelligent content selection."""
        return f"""
Extract the main article content from the following HTML. Your goal is to identify and return only the primary article text, removing all navigation, advertisements, comments, sidebars, headers, footers, and other non-essential content.

**Instructions:**

1. **Identify Main Content**: Look for the primary article content that someone would want to read or listen to. This typically includes:
   - Article title and headings
   - Main body paragraphs
   - Important quotes and citations
   - Relevant image captions (if they add value)
   - Key lists and bullet points

2. **Remove Non-Content**: Exclude all of the following:
   - Navigation menus and breadcrumbs
   - Advertisements and promotional content
   - "Related articles" or "You might also like" sections
   - Comments and user-generated content
   - Social media sharing buttons and widgets
   - Cookie notices and pop-ups
   - Website headers and footers
   - Author bios (unless essential to the article)
   - Subscription prompts and newsletter signups

3. **Content Quality**:
   - Preserve the logical flow and structure of the article
   - Keep important formatting cues (like paragraph breaks)
   - Maintain quotes and attributions
   - Include relevant subheadings that organize the content

4. **Output Format**: Return your response as JSON with a single key "extracted_content" containing the clean article text.

**Example Output:**
{{
  "extracted_content": "Article Title\\n\\nMain article content here with proper paragraph breaks and structure..."
}}

**Source URL:** {url}

**HTML Content:**
{html}
"""

    def _get_content_selection_model(self) -> str:
        """Get the model to use for content selection."""
        # Use the same model as content analysis, or fall back to gpt-4.1
        return getattr(settings, "OPENAI_CONTENT_ANALYSIS_MODEL", "gpt-4.1")
