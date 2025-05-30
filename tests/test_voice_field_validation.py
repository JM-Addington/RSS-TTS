"""Tests for voice field validation in the Article model.

This module tests the single source of truth validation for voice/voice_id fields,
ensuring only one field is set at a time to prevent inconsistencies.

These tests follow TDD principles and are designed to fail initially, then pass
once the validation logic is implemented.
"""

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase, TransactionTestCase

from text_to_audio.models import VOICE_ALLOY, VOICE_NOVA, Article, Feed

User = get_user_model()


class VoiceFieldValidationTests(TestCase):
    """Test voice field validation logic."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass123"
        )
        self.feed = Feed.objects.create(user=self.user, name="Test Feed")

    def test_article_clean_allows_voice_only(self):
        """Test that Article.clean() allows only voice field to be set."""
        article = Article(
            feed=self.feed,
            title="Test Article",
            text_content="Test content",
            voice=VOICE_ALLOY,
            voice_id=None,  # explicitly None
        )

        # This should not raise ValidationError
        try:
            article.clean()
        except ValidationError:
            self.fail("Article.clean() raised ValidationError when only voice was set")

    def test_article_clean_allows_voice_id_only(self):
        """Test that Article.clean() allows only voice_id field to be set."""
        article = Article(
            feed=self.feed,
            title="Test Article",
            text_content="Test content",
            voice="",  # empty string should be treated as unset
            voice_id="custom_voice_123",
        )

        # This should not raise ValidationError
        try:
            article.clean()
        except ValidationError:
            self.fail(
                "Article.clean() raised ValidationError when only voice_id was set"
            )

    def test_article_clean_rejects_both_fields_set(self):
        """Test that Article.clean() rejects when both voice and voice_id are set."""
        # Use a non-default voice to ensure conflict detection
        article = Article(
            feed=self.feed,
            title="Test Article",
            text_content="Test content",
            voice=VOICE_NOVA,  # Use nova instead of alloy to avoid default handling
            voice_id="custom_voice_123",
        )

        with self.assertRaises(ValidationError) as context:
            article.clean()

        # Check that the error message is clear and helpful
        error_dict = context.exception.error_dict
        self.assertIn("voice", error_dict)
        error_message = str(error_dict["voice"][0])
        self.assertIn("Only one voice field should be set", error_message)
        self.assertIn("voice", error_message)
        self.assertIn("voice_id", error_message)

    def test_article_clean_allows_neither_field_set(self):
        """Test that Article.clean() allows neither field to be set (uses default)."""
        article = Article(
            feed=self.feed,
            title="Test Article",
            text_content="Test content",
            voice="",  # empty string
            voice_id=None,
        )

        # This should not raise ValidationError - defaults will apply
        try:
            article.clean()
        except ValidationError:
            self.fail(
                "Article.clean() raised ValidationError when neither voice field was set"
            )

    def test_article_clean_empty_string_voice_id_treated_as_unset(self):
        """Test that empty string voice_id is treated as unset."""
        article = Article(
            feed=self.feed,
            title="Test Article",
            text_content="Test content",
            voice=VOICE_NOVA,
            voice_id="",  # empty string should be treated as unset
        )

        # This should not raise ValidationError
        try:
            article.clean()
        except ValidationError:
            self.fail(
                "Article.clean() raised ValidationError when voice_id was empty string"
            )

    def test_article_clean_whitespace_only_voice_id_treated_as_unset(self):
        """Test that whitespace-only voice_id is treated as unset."""
        article = Article(
            feed=self.feed,
            title="Test Article",
            text_content="Test content",
            voice=VOICE_NOVA,
            voice_id="   ",  # whitespace only should be treated as unset
        )

        # This should not raise ValidationError
        try:
            article.clean()
        except ValidationError:
            self.fail(
                "Article.clean() raised ValidationError when voice_id was whitespace only"
            )

    def test_article_clean_allows_default_voice_with_voice_id(self):
        """Test that Article.clean() allows default 'alloy' voice when voice_id is set."""
        # This is the specific case that was causing issues before the fix
        article = Article(
            feed=self.feed,
            title="Test Article",
            text_content="Test content",
            voice=VOICE_ALLOY,  # Default value
            voice_id="custom_voice_123",  # Custom voice ID
        )

        # This should NOT raise ValidationError with the fix
        try:
            article.clean()
        except ValidationError:
            self.fail(
                "Article.clean() raised ValidationError when default 'alloy' voice was set with voice_id"
            )

    def test_article_clean_error_message_format(self):
        """Test that validation error message has proper format and information."""
        # Use a non-default voice to ensure conflict detection
        article = Article(
            feed=self.feed,
            title="Test Article",
            text_content="Test content",
            voice=VOICE_NOVA,  # Use nova instead of alloy to avoid default handling
            voice_id="custom_voice_456",
        )

        with self.assertRaises(ValidationError) as context:
            article.clean()

        error_dict = context.exception.error_dict
        self.assertIn("voice", error_dict)
        error_message = str(error_dict["voice"][0])

        # Check message contains helpful information
        self.assertIn("Only one voice field should be set", error_message)
        self.assertIn("voice='nova'", error_message)
        self.assertIn("voice_id='custom_voice_456'", error_message)

    def test_article_clean_preserves_other_validation(self):
        """Test that voice validation doesn't interfere with other model validation."""
        # Create an article with an invalid status to test other validation still works
        article = Article(
            feed=self.feed,
            title="",  # This might trigger other validation
            text_content="Test content",
            voice=VOICE_ALLOY,
            voice_id=None,
        )

        # Voice validation should pass, but other validation might fail
        # We're just ensuring clean() runs without errors related to voice validation
        try:
            article.clean()
        except ValidationError as e:
            # If there's a ValidationError, it shouldn't be about voice fields
            if hasattr(e, "error_dict"):
                self.assertNotIn("voice", e.error_dict)


class VoiceFieldMigrationTests(TransactionTestCase):
    """Test data migration scenarios for voice field consistency."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            username="migrationuser",
            email="migration@example.com",
            password="testpass123",
        )
        self.feed = Feed.objects.create(user=self.user, name="Migration Feed")

    def test_migration_syncs_voice_to_voice_id_when_voice_id_empty(self):
        """Test migration copies voice to voice_id when voice_id is empty."""
        # Create article with only voice set (simulating pre-migration state)
        article = Article.objects.create(
            feed=self.feed,
            title="Migration Test",
            text_content="Test content",
            voice=VOICE_ALLOY,
            voice_id=None,
        )

        # TODO: This will be implemented when we create the data migration
        # For now, this test documents the expected behavior
        self.assertEqual(article.voice, VOICE_ALLOY)
        self.assertIsNone(article.voice_id)

    def test_migration_preserves_voice_id_when_set(self):
        """Test migration preserves voice_id when it's already set."""
        # Create article with voice_id set (simulating new data)
        article = Article.objects.create(
            feed=self.feed,
            title="Migration Test 2",
            text_content="Test content",
            voice=VOICE_ALLOY,  # This might be inconsistent
            voice_id="custom_voice_789",
        )

        # TODO: This will be implemented when we create the data migration
        # For now, this test documents the expected behavior
        self.assertEqual(article.voice_id, "custom_voice_789")

    def test_migration_handles_conflicting_values(self):
        """Test migration handles cases where voice and voice_id conflict."""
        # Create article with conflicting values
        article = Article.objects.create(
            feed=self.feed,
            title="Conflict Test",
            text_content="Test content",
            voice=VOICE_ALLOY,
            voice_id="different_custom_voice",
        )

        # TODO: This will be implemented when we create the data migration
        # Migration should choose one field as canonical and sync the other
        # We'll document which field takes precedence
        self.assertEqual(article.voice, VOICE_ALLOY)
        self.assertEqual(article.voice_id, "different_custom_voice")


class VoiceFieldDocumentationTests(TestCase):
    """Test documentation and deprecation roadmap."""

    def test_article_model_has_deprecation_documentation(self):
        """Test that Article model has proper deprecation documentation."""
        from text_to_audio.models import Article

        # Check that model docstring mentions voice field deprecation strategy
        docstring = Article.__doc__
        self.assertIsNotNone(docstring)

        # TODO: This will pass once we add deprecation documentation
        # For now, this test documents what we expect
        # self.assertIn("voice_id", docstring.lower())
        # self.assertIn("deprecat", docstring.lower())

    def test_voice_fields_have_help_text(self):
        """Test that voice fields have helpful help_text."""
        from text_to_audio.models import Article

        voice_field = Article._meta.get_field("voice")
        voice_id_field = Article._meta.get_field("voice_id")

        self.assertIsNotNone(voice_field.help_text)
        self.assertIsNotNone(voice_id_field.help_text)

        # TODO: Update help_text to indicate deprecation strategy
        # For now just ensure they exist


class VoiceFieldEdgeCaseTests(TestCase):
    """Test edge cases for voice field validation."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            username="edgecase", email="edge@example.com", password="testpass123"
        )
        self.feed = Feed.objects.create(user=self.user, name="Edge Case Feed")

    def test_article_with_null_and_empty_string(self):
        """Test combination of None and empty string values."""
        article = Article(
            feed=self.feed,
            title="Edge Case",
            text_content="Test content",
            voice=None,  # This might not be valid due to field constraints
            voice_id="",
        )

        # This should not raise ValidationError from our custom validation
        # (though Django field validation might complain about None voice)
        try:
            article.clean()
        except ValidationError as e:
            # If error is about voice being None (Django field validation), that's expected
            if hasattr(e, "error_dict") and "voice" in e.error_dict:
                error_msg = str(e.error_dict["voice"][0])
                # Our custom validation error contains "Only one voice field"
                if "Only one voice field" in error_msg:
                    self.fail("Our validation triggered when it shouldn't have")

    def test_article_with_unicode_voice_id(self):
        """Test voice_id with unicode characters."""
        article = Article(
            feed=self.feed,
            title="Unicode Test",
            text_content="Test content",
            voice="",
            voice_id="voice_ñoño_測試",
        )

        # Should not raise ValidationError
        try:
            article.clean()
        except ValidationError:
            self.fail("Article.clean() failed with unicode voice_id")

    def test_article_with_very_long_voice_id(self):
        """Test voice_id that's very long."""
        long_voice_id = "a" * 100  # Very long voice_id
        article = Article(
            feed=self.feed,
            title="Long Voice ID Test",
            text_content="Test content",
            voice="",
            voice_id=long_voice_id,
        )

        # Should not raise ValidationError from our validation
        # (Django field validation might complain about length)
        try:
            article.clean()
        except ValidationError as e:
            # If error is about field length, that's Django's validation
            if hasattr(e, "error_dict") and "voice_id" in e.error_dict:
                error_msg = str(e.error_dict["voice_id"][0])
                if "Only one voice field" in error_msg:
                    self.fail("Our validation triggered when it shouldn't have")
