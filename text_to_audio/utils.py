"""Utilities for the text_to_audio app.

This module provides utility functions for the RSS-to-TTS system, including
URL content extraction and text processing.
"""

import logging
from typing import List, Optional, Tuple

import requests
from bs4 import BeautifulSoup, Tag

# Configure logging
logger = logging.getLogger(__name__)


def fetch_url_content(url: str, timeout: int = 10) -> Tuple[bool, str, Optional[str]]:
    """Fetch HTML content from a URL.

    Args:
        url: The URL to fetch content from.
        timeout: Request timeout in seconds.

    Returns:
        Tuple of (success, content, error_message).
        If successful, error_message will be None.
    """
    try:
        response = requests.get(url, timeout=timeout)
        response.raise_for_status()
        return True, response.text, None
    except requests.RequestException as e:
        error_message = f"Error fetching URL {url}: {str(e)}"
        logger.error(error_message)
        return False, "", error_message


def _find_main_container(soup: BeautifulSoup) -> Optional[Tag]:
    """Find the main content container in an HTML document.

    Args:
        soup: BeautifulSoup object of the HTML document.

    Returns:
        The main content container Tag, or None if not found.
    """
    # Look for article first, then main, then fall back to the whole body
    return soup.find("article") or soup.find("main") or soup.body


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
        alt = img.get("alt")
        if alt and alt.strip():
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
        caption = table.find("caption")
        if caption and caption.get_text(strip=True):
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
    # Fetch the HTML content
    success, html, error = fetch_url_content(url)
    if not success:
        return False, "", error

    # Extract the article text
    success, text, error = extract_article_text(html)
    if not success:
        return False, "", error

    return True, text, None
