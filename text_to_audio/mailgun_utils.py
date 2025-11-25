"""Utilities for Mailgun email address generation and management."""

import hashlib
import uuid


# AIDEV-NOTE: Word lists for generating readable email addresses
# These are common, simple words that are easy to read and type
ADJECTIVES = [
    "happy", "bright", "swift", "calm", "bold", "wise", "kind", "grand",
    "clever", "gentle", "proud", "brave", "fair", "noble", "pure", "keen",
    "merry", "lively", "eager", "quick", "warm", "cool", "fresh", "crisp",
    "silver", "golden", "crystal", "amber", "ruby", "jade", "pearl", "azure"
]

NOUNS = [
    "river", "mountain", "forest", "ocean", "meadow", "valley", "canyon", "peak",
    "lake", "stream", "island", "harbor", "bridge", "tower", "castle", "garden",
    "cloud", "moon", "star", "sun", "comet", "aurora", "thunder", "breeze",
    "fox", "bear", "eagle", "deer", "wolf", "hawk", "raven", "owl"
]


def generate_feed_email_address(feed_token: uuid.UUID, domain: str) -> str:
    """Generate a deterministic, readable email address for a feed.

    Uses the feed's UUID token to generate a consistent email address
    that can be regenerated from the same token. Format: adjective-noun-number@domain

    Args:
        feed_token: The feed's UUID token
        domain: The Mailgun domain (e.g., "mg.example.com")

    Returns:
        A readable email address like "happy-river-42@mg.example.com"

    Example:
        >>> token = uuid.UUID("12345678-1234-5678-1234-567812345678")
        >>> generate_feed_email_address(token, "mg.example.com")
        'crystal-eagle-23@mg.example.com'
    """
    # Convert UUID to bytes and hash it for deterministic random numbers
    token_bytes = feed_token.bytes
    hash_obj = hashlib.sha256(token_bytes)
    hash_digest = hash_obj.digest()

    # Use different parts of the hash for different selections
    # This ensures we get different values for adjective, noun, and number
    adjective_index = int.from_bytes(hash_digest[0:4], byteorder='big') % len(ADJECTIVES)
    noun_index = int.from_bytes(hash_digest[4:8], byteorder='big') % len(NOUNS)
    number = int.from_bytes(hash_digest[8:10], byteorder='big') % 100  # 0-99

    adjective = ADJECTIVES[adjective_index]
    noun = NOUNS[noun_index]

    return f"{adjective}-{noun}-{number}@{domain}"


def parse_feed_email_recipient(recipient_email: str) -> str | None:
    """Extract the local part from a feed email address.

    Args:
        recipient_email: Full email address (e.g., "happy-river-42@mg.example.com")

    Returns:
        The local part (e.g., "happy-river-42") or None if invalid format

    Example:
        >>> parse_feed_email_recipient("happy-river-42@mg.example.com")
        'happy-river-42'
    """
    if not recipient_email or "@" not in recipient_email:
        return None

    local_part, _ = recipient_email.split("@", 1)
    return local_part.lower()


def validate_mailgun_domain(domain: str) -> bool:
    """Validate that a Mailgun domain is properly formatted.

    Args:
        domain: The domain to validate (e.g., "mg.example.com")

    Returns:
        True if valid, False otherwise
    """
    if not domain:
        return False

    # Basic validation: must contain at least one dot and no @
    if "@" in domain:
        return False

    if "." not in domain:
        return False

    # Must not be empty or just whitespace
    if not domain.strip():
        return False

    return True
