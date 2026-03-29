"""Utilities for the text_to_audio app.

This module provides utility functions for the RSS-to-TTS system, including
URL content extraction and text processing.
"""

import json
import logging
import re
import time
from typing import Any, Dict, List, Optional, Tuple

import PyPDF2
import requests
from bs4 import BeautifulSoup, Comment, Tag
from django.conf import settings

# Configure logging
logger = logging.getLogger(__name__)


def extract_text_from_pdf(file_obj) -> str:
    """Extract text content from a PDF file.

    Args:
        file_obj: A file object representing the PDF file.

    Returns:
        The extracted text content, or an error message if extraction fails.
    """
    try:
        reader = PyPDF2.PdfReader(file_obj)
        text_parts = []
        for page_num in range(len(reader.pages)):
            page = reader.pages[page_num]
            text_parts.append(page.extract_text())
        return "\n".join(text_parts)
    except Exception as e:
        logger.error(f"Error extracting text from PDF: {str(e)}")
        return f"Error: Could not extract text from PDF. {str(e)}"


def extract_title_from_html(html: str) -> str:
    """Extract the title from HTML content.

    Args:
        html: The HTML content to extract the title from.

    Returns:
        The extracted title, or an empty string if no title found.
    """
    try:
        soup = BeautifulSoup(html, "html.parser")
        title_tag = soup.find("title")
        if title_tag and title_tag.text:
            return str(title_tag.text.strip())
        return ""
    except Exception as e:
        logger.error(f"Error extracting title: {str(e)}")
        return ""


def sanitize_text_for_tts(text: Optional[str]) -> str:
    """Sanitize text for TTS by removing URLs, markdown syntax, and HTML.

    AIDEV-NOTE: This function ensures clean text is sent to TTS providers.
    Google TTS in particular fails on long URLs which appear as one "sentence".
    Called at the TTSService boundary to prevent TTS API errors.

    Args:
        text: The raw text that may contain URLs, markdown, or HTML artifacts.
              Can be None, which returns an empty string.

    Returns:
        Cleaned text suitable for TTS synthesis.
    """
    if not text:
        return ""

    result = text

    # Remove markdown image syntax: ![alt](url) or ![alt][ref]
    result = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", result)
    result = re.sub(r"!\[[^\]]*\]\[[^\]]*\]", "", result)

    # Remove markdown link syntax but keep link text: [text](url) -> text
    result = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", result)
    result = re.sub(r"\[([^\]]*)\]\[[^\]]*\]", r"\1", result)

    # Remove bare markdown-style URLs in brackets: [https://...]
    result = re.sub(r"\[https?://[^\]]+\]", "", result)

    # Remove angle-bracket URLs: <https://...>
    result = re.sub(r"<https?://[^>]+>", "", result)

    # Remove raw URLs (http/https)
    result = re.sub(r"https?://[^\s<>\[\]()\"']+", "", result)

    # Remove any remaining HTML tags
    result = re.sub(r"<[^>]+>", "", result)

    # Remove email addresses (often appear in newsletters)
    result = re.sub(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", "", result)

    # Clean up multiple consecutive whitespace (but preserve paragraph breaks)
    result = re.sub(r"[ \t]+", " ", result)  # Multiple spaces/tabs to single space
    result = re.sub(r"\n{3,}", "\n\n", result)  # Max 2 consecutive newlines
    result = re.sub(
        r"^\s+", "", result, flags=re.MULTILINE
    )  # Leading whitespace on lines

    # Remove empty parentheses/brackets that may remain
    result = re.sub(r"\(\s*\)", "", result)
    result = re.sub(r"\[\s*\]", "", result)

    # Clean up any remaining artifacts
    result = result.strip()

    return result


def _handle_http_error(status_code: int, url: str) -> Optional[Tuple[bool, str, str]]:
    """Handle common HTTP error status codes.

    Args:
        status_code: The HTTP status code to handle.
        url: The URL that was accessed.

    Returns:
        None if the status code is 200 or a server error that should be retried,
        or a tuple with (success, content, error_message) otherwise.
    """
    if status_code == 404:
        return (
            False,
            "",
            f"404 Not Found: The requested page '{url}' could not be found.",
        )
    elif status_code == 403:
        return (
            False,
            "",
            f"403 Forbidden: Access to '{url}' is forbidden. "
            f"The site may require authentication or block automated access.",
        )
    elif status_code == 500:
        # Server error - should be retried
        return None
    elif status_code != 200:
        return (
            False,
            "",
            f"HTTP Error {status_code}: Unable to access '{url}'.",
        )

    # Status code is 200 (success)
    return None


def _handle_retry(retry_count: int, max_retries: int, url: str, error: str) -> None:
    """Handle retry logic with exponential backoff.

    Args:
        retry_count: Current retry count.
        max_retries: Maximum number of retries allowed.
        url: The URL being accessed.
        error: Error message to log.
    """
    logger.warning(f"Attempt {retry_count}/{max_retries}: {error} for {url}")
    if retry_count < max_retries:
        # Exponential backoff
        time.sleep(2**retry_count)


def fetch_url_content(
    url: str, timeout: int = 10, max_retries: int = 5
) -> Tuple[bool, str, Optional[str]]:
    """Fetch HTML content from a URL with retry mechanism.

    Args:
        url: The URL to fetch content from.
        timeout: Request timeout in seconds.
        max_retries: Maximum number of retry attempts for recoverable errors.

    Returns:
        Tuple of (success, content, error_message).
        If successful, error_message will be None.
    """
    # AIDEV-NOTE: Defense-in-depth SSRF check — re-validates before fetch (#190)
    try:
        from text_to_audio.validators import validate_url_not_ssrf

        validate_url_not_ssrf(url)
    except Exception as ssrf_exc:
        logger.warning("SSRF check blocked URL in fetch_url_content: %s — %s", url, ssrf_exc)
        return False, "", f"URL blocked by security policy: {ssrf_exc}"

    retry_count = 0
    last_error = None

    while retry_count < max_retries:
        try:
            logger.info(
                f"Fetching URL: {url} (Attempt {retry_count + 1}/{max_retries})"
            )
            response = requests.get(url, timeout=timeout)

            # Handle common HTTP error status codes
            result = _handle_http_error(response.status_code, url)
            if result:
                return result

            # Handle server error (status code 500)
            if response.status_code == 500:
                last_error = (
                    f"500 Server Error: The server at '{url}' encountered an error."
                )
                retry_count += 1
                _handle_retry(retry_count, max_retries, url, "Server error")
                continue

            # Success - return the content
            return True, response.text, None

        except requests.Timeout:
            last_error = f"Connection timed out after {timeout} seconds."
            retry_count += 1
            _handle_retry(retry_count, max_retries, url, "Timeout")

        except requests.ConnectionError:
            last_error = (
                f"Connection Error: Unable to connect to '{url}'. "
                f"The site may be down or the URL may be invalid."
            )
            retry_count += 1
            _handle_retry(retry_count, max_retries, url, "Connection error")

        except requests.RequestException as e:
            error_message = f"Error fetching URL {url}: {str(e)}"
            logger.error(error_message)
            return False, "", error_message

    # If we've exhausted our retries
    logger.error(f"Max retries ({max_retries}) exceeded for URL {url}: {last_error}")
    return False, "", f"Failed after {max_retries} attempts: {last_error}"


def fetch_html_with_firecrawl(url: str) -> Tuple[bool, str, Optional[str]]:
    """Fetch HTML content using the Firecrawl API.

    Args:
        url: The URL to fetch via Firecrawl.

    Returns:
        Tuple of (success, html, error_message).
    """
    from appconfig.utils import get_firecrawl_api_key

    api_key = get_firecrawl_api_key()
    if not api_key:
        return False, "", "Firecrawl API key not configured"

    endpoint = getattr(
        settings,
        "FIRECRAWL_ENDPOINT",
        "https://api.firecrawl.dev/v1/scrape",
    )

    try:
        response = requests.post(
            endpoint,
            json={"url": url, "formats": ["html"]},
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=20,
        )

        if response.status_code != 200:
            logger.error(
                "Firecrawl request failed with status %s", response.status_code
            )
            return (
                False,
                "",
                f"Firecrawl Error {response.status_code}: {response.text}",
            )

        data = response.json()

        # The new API returns data in the 'data' field
        if "data" in data:
            html = data["data"].get("html", "")
        else:
            # Fallback for older API responses
            html = data.get("html") or data.get("content", "")

        if not html:
            return False, "", "Firecrawl response contained no HTML"

        return True, str(html), None

    except Exception as exc:  # pragma: no cover - safeguard
        logger.error("Firecrawl request error: %s", exc)
        return False, "", f"Firecrawl request failed: {exc}"


def _find_main_container(soup: BeautifulSoup) -> Optional[Tag]:
    """Find the main content container in an HTML document.

    Args:
        soup: BeautifulSoup object of the HTML document.

    Returns:
        The main content container Tag, or None if not found.
    """
    # Look for article first, then main, then fall back to the whole body
    article = soup.find("article")
    if isinstance(article, Tag):
        return article

    main = soup.find("main")
    if isinstance(main, Tag):
        return main

    body = soup.body
    if isinstance(body, Tag):
        return body

    return None


def _extract_text_elements(container: Tag) -> List[str]:
    """Extract text from heading and paragraph elements.

    Args:
        container: HTML container to extract text from.

    Returns:
        List of extracted text strings.
    """
    text_parts = []

    # Get headings and paragraphs
    for tag in container.find_all(["h1", "h2", "h3", "h4", "h5", "h6", "p", "li"]):
        if tag.get_text(strip=True):
            text_parts.append(tag.get_text(strip=True))

    return text_parts


def _extract_image_descriptions(container: Tag) -> List[str]:
    """Extract alt text descriptions from images.

    Args:
        container: HTML container to extract from.

    Returns:
        List of image description strings.
    """
    descriptions = []

    for element in container.find_all("img"):
        # Ensure we're working with a Tag object
        if not isinstance(element, Tag):
            continue

        alt = element.get("alt")
        if alt and isinstance(alt, str) and alt.strip():
            descriptions.append(f"[Image: {alt}]")

    return descriptions


def _extract_table_captions(container: Tag) -> List[str]:
    """Extract captions from tables.

    Args:
        container: HTML container to extract from.

    Returns:
        List of table caption strings.
    """
    captions = []

    for table_element in container.find_all("table"):
        if not isinstance(table_element, Tag):
            continue

        caption_element = table_element.find("caption")
        if isinstance(caption_element, Tag) and caption_element.get_text(strip=True):
            captions.append(f"[Table: {caption_element.get_text(strip=True)}]")
        else:
            captions.append("[Table present]")

    return captions


def extract_article_text(html: str) -> Tuple[bool, str, Optional[str]]:
    """Extract article text from HTML content.

    Uses BeautifulSoup to identify and extract the main content of an article,
    including headings, paragraphs, and list items. Also extracts image alt text
    and table captions when available.

    Args:
        html: The HTML content to extract text from.

    Returns:
        Tuple of (success, extracted_text, error_message).
        If successful, error_message will be None.
    """
    try:
        soup = BeautifulSoup(html, "html.parser")

        # Find the main container
        main_container = _find_main_container(soup)
        if not main_container:
            return False, "", "Could not identify main content container"

        # Extract all content parts
        text_parts = []
        text_parts.extend(_extract_text_elements(main_container))
        text_parts.extend(_extract_image_descriptions(main_container))
        text_parts.extend(_extract_table_captions(main_container))

        # Join all text parts with newlines
        extracted_text = "\n".join(text_parts)

        if not extracted_text.strip():
            return False, "", "No content could be extracted from the page"

        return True, extracted_text, None

    except Exception as e:
        error_message = f"Error extracting article text: {str(e)}"
        logger.error(error_message)
        return False, "", error_message


def clean_html_minimal(html: str) -> str:
    """Clean HTML by removing only unwanted tags and attributes.

    This function removes script, style, and other non-content tags,
    as well as attributes like class, id, and style that aren't needed
    for content extraction.

    Args:
        html: Raw HTML content

    Returns:
        Cleaned HTML with only content-relevant tags and attributes
    """
    try:
        soup = BeautifulSoup(html, "html.parser")

        # Remove unwanted tags completely
        unwanted_tags = [
            "script",
            "style",
            "meta",
            "link",
            "noscript",
            "iframe",
            "embed",
            "object",
            "param",
            "svg",
            "canvas",
            "map",
            "area",
            "audio",
            "video",
            "source",
            "track",
            "form",
            "input",
            "button",
            "select",
            "option",
            "textarea",
            "label",
            "fieldset",
            "legend",
            "datalist",
            "output",
            "progress",
            "meter",
            "details",
            "summary",
            "menu",
            "menuitem",
            "dialog",
        ]

        for tag in unwanted_tags:
            for element in soup.find_all(tag):
                element.decompose()

        # Remove comments
        for comment in soup.find_all(string=lambda text: isinstance(text, Comment)):
            comment.extract()

        # Remove unwanted attributes from all remaining tags
        for element in soup.find_all(True):  # Find all tags
            # Ensure we're working with a Tag object
            if not isinstance(element, Tag):
                continue

            # Keep only href for links and src/alt for images
            attrs_to_keep = {}
            if element.name == "a" and element.get("href"):
                attrs_to_keep["href"] = element.get("href", "")
            elif element.name == "img":
                if element.get("src"):
                    attrs_to_keep["src"] = element.get("src", "")
                if element.get("alt"):
                    attrs_to_keep["alt"] = element.get("alt", "")

            # Clear all attributes and restore only the ones we want to keep
            element.attrs.clear()
            for key, value in attrs_to_keep.items():
                if value is not None:
                    element.attrs[key] = value

        # Return the cleaned HTML
        return str(soup)

    except Exception as e:
        logger.error(f"Error cleaning HTML: {str(e)}")
        return html  # Return original HTML if cleaning fails


def extract_article_text_with_gpt(
    html: str, url: str = ""
) -> Tuple[bool, str, Optional[str]]:
    """Extract article text using GPT-4.1 with cleaned HTML.

    This function first cleans the HTML to remove unnecessary tags and attributes,
    then uses GPT-4.1's large context window to intelligently extract the main
    article content.

    Args:
        html: The raw HTML content
        url: The source URL (optional, for context)

    Returns:
        Tuple of (success, extracted_text, error_message).
        If successful, error_message will be None.
    """
    try:
        # First, clean the HTML
        cleaned_html = clean_html_minimal(html)

        # Prepare the prompt for GPT-4.1
        prompt = f"""Extract the main article content from this HTML.
Return only the article text that should be narrated, including:
- The main title/headline
- All body paragraphs
- Any relevant quotes or excerpts
- Only include image descriptions from alt text or image captions if they are needed for context; skip credit lines (format as: [Image: description])
- Table data if present (format as: [Table: brief description])

Do not include:
- Navigation menus
- Advertisements
- Footer information
- Sidebar content
- Comments sections
- Related articles links
- Social media buttons
- Copyright notices

Source URL: {url}

HTML:
{cleaned_html}

EXTRACTED ARTICLE TEXT:"""

        # Use GPT-4.1 to extract the content
        import openai

        from appconfig.utils import get_openai_api_key

        client = openai.OpenAI(api_key=get_openai_api_key())

        # Log the API call
        start_time = time.monotonic()
        request_data = {
            "model": "gpt-4.1-2025-04-14",
            "messages": [
                {
                    "role": "system",
                    "content": "Extract the main article content from HTML.",
                },
                {"role": "user", "content": prompt},
            ],
            "max_tokens": 32768,
            "temperature": 0.1,  # Low temperature for consistent extraction
        }

        try:
            # Call the correct OpenAI API for chat completions
            response = client.chat.completions.create(**request_data)
            end_time = time.monotonic()
            duration_ms = int((end_time - start_time) * 1000)

            # Extract the content
            extracted_text = response.choices[0].message.content.strip()

            # Log the successful API call
            response_data = {
                "id": response.id,
                "model": response.model,
                "object": response.object,
                "created": response.created,
                "choices": [
                    {
                        "index": choice.index,
                        "message": {
                            "role": choice.message.role,
                            "content": (
                                choice.message.content[:500] + "..."
                                if len(choice.message.content) > 500
                                else choice.message.content
                            ),
                        },
                        "finish_reason": choice.finish_reason,
                    }
                    for choice in response.choices
                ],
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

            log_openai_api_call(
                operation="Article Content Extraction (GPT-4.1)",
                request_data=request_data,
                response_data=response_data,
                duration_ms=duration_ms,
            )

            if not extracted_text:
                return False, "", "GPT-4.1 could not extract any content from the page"

            return True, extracted_text, None

        except openai.APIError as e:
            error_msg = f"OpenAI API error: {str(e)}"
            logger.error(error_msg)
            return False, "", error_msg
        except Exception as e:
            error_msg = f"Error calling GPT-4.1: {str(e)}"
            logger.error(error_msg)
            return False, "", error_msg

    except Exception as e:
        error_message = f"Error in GPT-based extraction: {str(e)}"
        logger.error(error_message)
        return False, "", error_message


def process_url_to_text(url: str) -> Tuple[bool, str, Optional[str]]:
    """Process a URL to extract its textual content.

    Combines HTML fetching and text extraction logic with optional Firecrawl
    support.

    Args:
        url: The URL to process.

    Returns:
        Tuple of (success, extracted_text, error_message).
        If successful, error_message will be None.
    """
    from appconfig.utils import (get_firecrawl_api_key,
                                 get_use_firecrawl_by_default)

    html = ""
    success = False
    error: Optional[str] = None

    use_firecrawl_default = get_use_firecrawl_by_default()
    api_key = get_firecrawl_api_key()

    if use_firecrawl_default and api_key:
        success, html, error = fetch_html_with_firecrawl(url)
        if not success:
            logger.warning("Firecrawl default fetch failed for %s: %s", url, error)

    if not success:
        success, html, error = fetch_url_content(url, max_retries=1)

        if (
            not success
            and api_key
            and error
            and any(code in error for code in ["404", "403", "400"])
        ):
            fc_success, fc_html, fc_error = fetch_html_with_firecrawl(url)
            if fc_success:
                success, html, error = True, fc_html, None
            else:
                return False, "", fc_error or error

    if not success:
        return False, "", error

    # Try GPT-4.1 extraction first (if enabled)
    use_gpt_extraction = getattr(settings, "USE_GPT_FOR_URL_EXTRACTION", True)

    if use_gpt_extraction:
        success, text, error = extract_article_text_with_gpt(html, url)
        if success:
            return True, text, None
        else:
            # Log the error but fall back to traditional extraction
            logger.warning(
                f"GPT extraction failed for {url}: {error}. Falling back to traditional extraction."
            )
    # Fall back to traditional extraction
    success, text, error = extract_article_text(html)
    if not success:
        return False, "", error

    return True, text, None


def get_canonical_audio_path(user_id: int, article_id: int) -> str:
    """Get the canonical path for an article's audio file.

    Args:
        user_id: ID of the user who owns the article
        article_id: ID of the article

    Returns:
        The canonical path: media/audio/{user_id}/{article_id}.mp3
    """
    import os

    from django.conf import settings

    return os.path.join(settings.MEDIA_ROOT, "audio", str(user_id), f"{article_id}.mp3")


def safe_delete_audio_file(file_path: Optional[str]) -> bool:
    """Safely delete an audio file with directory protection.

    This function ensures that only audio files are deleted and prevents
    accidental deletion of directories or non-audio files.

    Args:
        file_path: Path to the audio file to delete.

    Returns:
        True if the file was successfully deleted, False otherwise.

    Raises:
        AssertionError: If the path is invalid, points to a directory,
                       or is not an audio file.
    """
    import os

    # Validate input
    assert file_path is not None, "Path cannot be None or empty"
    assert isinstance(file_path, str), "Path must be a string"
    assert file_path.strip() != "", "Path cannot be None or empty"

    file_path = file_path.strip()

    # Check if path exists first (for better error handling)
    if not os.path.exists(file_path):
        logger.info(f"File does not exist, skipping deletion: {file_path}")
        return False

    # Safety check: ensure we're not trying to delete a directory
    assert not os.path.isdir(file_path), f"Cannot delete directory: {file_path}"

    # Validate file extension - only allow audio files
    valid_audio_extensions = {".mp3", ".wav", ".m4a", ".ogg", ".flac", ".aac"}
    file_extension = os.path.splitext(file_path)[1].lower()
    assert file_extension in valid_audio_extensions, (
        f"Only audio files can be deleted. Got extension: {file_extension}. "
        f"Valid extensions: {', '.join(sorted(valid_audio_extensions))}"
    )

    try:
        # Actually delete the file
        os.unlink(file_path)
        logger.info(f"Successfully deleted audio file: {file_path}")
        return True

    except (OSError, FileNotFoundError, PermissionError) as e:
        logger.warning(f"Error deleting file {file_path}: {e}")
        return False


def redact_api_key(data: Any) -> Any:
    """Recursively redact API keys from data structures.

    Args:
        data: The data to redact API keys from (dict, list, str, etc.)

    Returns:
        The data with API keys redacted
    """
    # Define sensitive key patterns to redact
    sensitive_keys = {
        "api_key",
        "authorization",
        "secret",
        "password",
        "passwd",
        "token",
    }

    # Define keys to preserve (important for debugging)
    preserve_keys = {
        "prompt_tokens",
        "completion_tokens",
        "total_tokens",
        "max_tokens",
        "max_completion_tokens",
        "input_tokens",
        "output_tokens",
    }

    if isinstance(data, dict):
        redacted = {}
        for key, value in data.items():
            if isinstance(key, str):
                key_lower = key.lower()
                # Preserve important token usage metrics
                if key_lower in preserve_keys:
                    redacted[key] = value
                # Redact sensitive keys
                elif any(sensitive in key_lower for sensitive in sensitive_keys):
                    redacted[key] = "[REDACTED]"
                else:
                    redacted[key] = redact_api_key(value)
            else:
                redacted[key] = redact_api_key(value)
        return redacted
    elif isinstance(data, list):
        return [redact_api_key(item) for item in data]
    elif isinstance(data, str):
        # Redact bearer tokens and API keys in strings
        redacted_text = re.sub(
            r'(Bearer\s+|api[_-]?key["\s]*[:=]\s*["\']?)([a-zA-Z0-9_-]+)',
            r"\1[REDACTED]",
            data,
            flags=re.IGNORECASE,
        )
        # Redact sk- prefixed tokens (OpenAI format)
        redacted_text = re.sub(r"sk-[a-zA-Z0-9_-]+", "[REDACTED]", redacted_text)
        return redacted_text
    else:
        return data


def log_openai_api_call(
    operation: str,
    request_data: Dict[str, Any],
    response_data: Optional[Dict[str, Any]] = None,
    error: Optional[Exception] = None,
    duration_ms: Optional[int] = None,
) -> None:
    """Log OpenAI API calls with sensitive data redaction.

    Args:
        operation: Description of the operation (e.g., "TTS Generation", "Content Analysis")
        request_data: The request data sent to OpenAI
        response_data: The response data from OpenAI (if successful)
        error: Exception if the call failed
        duration_ms: Duration of the API call in milliseconds
    """
    # Create log entry structure
    log_entry = {
        "operation": operation,
        "timestamp": time.time(),
        "request": redact_api_key(request_data),
    }

    if duration_ms is not None:
        log_entry["duration_ms"] = duration_ms

    if error:
        log_entry["error"] = {
            "type": type(error).__name__,
            "message": str(error),
        }
        log_level = logging.ERROR
        status = "FAILED"
    else:
        log_entry["response"] = redact_api_key(response_data or {})
        log_level = logging.INFO
        status = "SUCCESS"

    # Log with structured format
    logger.log(
        log_level,
        f"OpenAI API Call [{status}] - {operation}: {json.dumps(log_entry, default=str, indent=2)}",
    )
