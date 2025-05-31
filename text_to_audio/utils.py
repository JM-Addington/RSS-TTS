"""Utilities for the text_to_audio app.

This module provides utility functions for the RSS-to-TTS system, including
URL content extraction and text processing.
"""

import json
import logging
import re
import time
from typing import Any, Dict, List, Optional, Tuple

import requests
from bs4 import BeautifulSoup, Tag

# Configure logging
logger = logging.getLogger(__name__)


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

    for img in container.find_all("img"):
        if not isinstance(img, Tag):
            continue

        alt = img.get("alt")
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

    for table in container.find_all("table"):
        if not isinstance(table, Tag):
            continue

        caption = table.find("caption")
        if isinstance(caption, Tag) and caption.get_text(strip=True):
            captions.append(f"[Table: {caption.get_text(strip=True)}]")
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


def process_url_to_text(url: str) -> Tuple[bool, str, Optional[str]]:
    """Process a URL to extract its textual content.

    Combines fetch_url_content and extract_article_text functions.

    Args:
        url: The URL to process.

    Returns:
        Tuple of (success, extracted_text, error_message).
        If successful, error_message will be None.
    """
    # Fetch the HTML content with retry mechanism
    success, html, error = fetch_url_content(url)
    if not success:
        return False, "", error

    # Extract the article text
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
