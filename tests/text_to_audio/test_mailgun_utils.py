"""Tests for Mailgun utilities."""

import unittest
import uuid

from text_to_audio.mailgun_utils import (
    generate_feed_email_address,
    parse_feed_email_recipient,
    validate_mailgun_domain,
)


class TestGenerateFeedEmailAddress(unittest.TestCase):
    """Tests for generate_feed_email_address function."""

    def test_generates_consistent_email_for_same_token(self):
        """Email address should be deterministic based on token."""
        token = uuid.UUID("12345678-1234-5678-1234-567812345678")
        domain = "mg.example.com"

        email1 = generate_feed_email_address(token, domain)
        email2 = generate_feed_email_address(token, domain)

        self.assertEqual(email1, email2)
        self.assertIn("@", email1)
        self.assertTrue(email1.endswith(f"@{domain}"))

    def test_generates_different_emails_for_different_tokens(self):
        """Different tokens should generate different email addresses."""
        token1 = uuid.UUID("12345678-1234-5678-1234-567812345678")
        token2 = uuid.UUID("87654321-4321-8765-4321-876543218765")
        domain = "mg.example.com"

        email1 = generate_feed_email_address(token1, domain)
        email2 = generate_feed_email_address(token2, domain)

        self.assertNotEqual(email1, email2)

    def test_email_format_is_adjective_noun_number(self):
        """Email should follow adjective-noun-number@domain format."""
        token = uuid.UUID("12345678-1234-5678-1234-567812345678")
        domain = "mg.example.com"

        email = generate_feed_email_address(token, domain)
        local_part, domain_part = email.split("@")

        # Should have three parts separated by hyphens
        parts = local_part.split("-")
        self.assertEqual(len(parts), 3, f"Expected 3 parts, got {len(parts)}: {parts}")

        # Third part should be a number
        self.assertTrue(parts[2].isdigit(), f"Third part should be numeric: {parts[2]}")
        number = int(parts[2])
        self.assertGreaterEqual(number, 0)
        self.assertLess(number, 100)

    def test_respects_provided_domain(self):
        """Generated email should use the provided domain."""
        token = uuid.uuid4()
        domain = "custom.mailgun.org"

        email = generate_feed_email_address(token, domain)

        self.assertTrue(email.endswith(f"@{domain}"))


class TestParseFeedEmailRecipient(unittest.TestCase):
    """Tests for parse_feed_email_recipient function."""

    def test_parses_valid_email(self):
        """Should extract local part from valid email."""
        email = "happy-river-42@mg.example.com"
        result = parse_feed_email_recipient(email)
        self.assertEqual(result, "happy-river-42")

    def test_handles_uppercase(self):
        """Should convert to lowercase."""
        email = "Happy-River-42@mg.example.com"
        result = parse_feed_email_recipient(email)
        self.assertEqual(result, "happy-river-42")

    def test_returns_none_for_invalid_email(self):
        """Should return None for invalid email formats."""
        self.assertIsNone(parse_feed_email_recipient(""))
        self.assertIsNone(parse_feed_email_recipient("no-at-sign"))
        self.assertIsNone(parse_feed_email_recipient(None))

    def test_handles_multiple_at_signs(self):
        """Should handle emails with multiple @ signs gracefully."""
        email = "local@part@domain.com"
        result = parse_feed_email_recipient(email)
        # Should split on first @ only
        self.assertEqual(result, "local")


class TestValidateMailgunDomain(unittest.TestCase):
    """Tests for validate_mailgun_domain function."""

    def test_accepts_valid_domain(self):
        """Should accept properly formatted domains."""
        self.assertTrue(validate_mailgun_domain("mg.example.com"))
        self.assertTrue(validate_mailgun_domain("mail.mysite.org"))
        self.assertTrue(validate_mailgun_domain("subdomain.mail.example.com"))

    def test_rejects_invalid_domains(self):
        """Should reject improperly formatted domains."""
        self.assertFalse(validate_mailgun_domain(""))
        self.assertFalse(validate_mailgun_domain("   "))
        self.assertFalse(validate_mailgun_domain("no-dot"))
        self.assertFalse(validate_mailgun_domain("has@at-sign.com"))
        self.assertFalse(validate_mailgun_domain(None))


if __name__ == "__main__":
    unittest.main()
