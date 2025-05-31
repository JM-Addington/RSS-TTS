"""Tests to verify that 'verse' voice has been properly removed."""

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import TestCase

from text_to_audio.models import Article, Feed, UserVoicePreset


class VerseVoiceRemovalTest(TestCase):
    """Test that 'verse' voice is no longer accepted."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            username="testuser", password="password123"
        )
        self.feed = Feed.objects.create(user=self.user, name="Test Feed")

    def test_article_cannot_use_verse_voice(self):
        """Test that creating an article with 'verse' voice raises ValidationError."""
        # Attempt to create an article with 'verse' voice
        article = Article(
            feed=self.feed,
            title="Test Article",
            text_content="This is a test article.",
            voice="verse",
        )

        # This should raise a ValidationError because 'verse' is not in VOICE_CHOICES
        with self.assertRaises(ValidationError) as context:
            article.full_clean()

        # Check that the error is about invalid choice
        self.assertIn("voice", context.exception.error_dict)
        error_messages = [str(e) for e in context.exception.error_dict["voice"]]
        self.assertTrue(
            any("is not a valid choice" in msg for msg in error_messages),
            f"Expected 'is not a valid choice' error, got: {error_messages}",
        )

    def test_voice_preset_cannot_use_verse(self):
        """Test that creating a voice preset with 'verse' raises ValidationError."""
        # Attempt to create a preset with 'verse' voice
        preset = UserVoicePreset(
            user=self.user, name="Test Preset", voice_id="verse", speed=1.0
        )

        # This should raise a ValidationError
        with self.assertRaises(ValidationError) as context:
            preset.full_clean()

        # Check that the error is about invalid choice
        self.assertIn("voice_id", context.exception.error_dict)
        error_messages = [str(e) for e in context.exception.error_dict["voice_id"]]
        self.assertTrue(
            any("is not a valid choice" in msg for msg in error_messages),
            f"Expected 'is not a valid choice' error, got: {error_messages}",
        )

    def test_verse_not_in_voice_choices(self):
        """Test that 'verse' is not in the available voice choices."""
        from text_to_audio.models import VOICE_CHOICES

        voice_ids = [choice[0] for choice in VOICE_CHOICES]
        self.assertNotIn("verse", voice_ids)

        # Verify all expected voices are present
        expected_voices = {
            "alloy",
            "ash",
            "ballad",
            "coral",
            "echo",
            "fable",
            "onyx",
            "nova",
            "sage",
            "shimmer",
        }
        self.assertEqual(set(voice_ids), expected_voices)

    def test_article_accepts_valid_voices(self):
        """Test that articles can still be created with valid voices."""
        valid_voices = ["alloy", "nova", "echo", "shimmer"]

        for voice in valid_voices:
            article = Article(
                feed=self.feed,
                title=f"Test Article {voice}",
                text_content="This is a test article.",
                voice=voice,
            )
            # Should not raise any validation errors
            article.full_clean()
            article.save()
            self.assertEqual(article.voice, voice)
