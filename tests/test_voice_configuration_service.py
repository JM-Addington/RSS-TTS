"""Tests for VoiceConfigurationService speed handling.

This module tests the critical bug fix for string speed values being properly
converted to floats in the VoiceConfigurationService.
"""

import logging
from unittest import TestCase
from unittest.mock import Mock

from text_to_audio.services.voice_configuration import VoiceConfigurationService


class VoiceConfigurationServiceSpeedTests(TestCase):
    """Test VoiceConfigurationService speed conversion and validation."""

    def setUp(self):
        """Set up test service."""
        self.service = VoiceConfigurationService()

    def test_get_voice_config_converts_string_speed_to_float(self):
        """Test that string speed values are converted to float."""
        # This tests the critical bug fix - string speeds should be converted to float
        config = self.service.get_voice_config(
            detected_tone="formal",
            user_preferences={"speed": "1.25"},  # String speed from form
        )

        # Speed should be converted to float and properly clamped
        self.assertIsInstance(config["speed"], float)
        self.assertEqual(config["speed"], 1.25)

    def test_get_voice_config_handles_numeric_string_speeds(self):
        """Test various numeric string speeds are handled correctly."""
        test_cases = [
            ("0.75", 0.75),  # Minimum valid speed
            ("1.0", 1.0),  # Normal speed
            ("1.25", 1.25),  # Fast speed
            ("1.5", 1.5),  # Maximum valid speed
            ("0.5", 0.75),  # Below minimum, should be clamped
            ("2.0", 1.5),  # Above maximum, should be clamped
        ]

        for string_speed, expected_float in test_cases:
            with self.subTest(string_speed=string_speed):
                config = self.service.get_voice_config(
                    detected_tone="neutral", user_preferences={"speed": string_speed}
                )
                self.assertIsInstance(config["speed"], float)
                self.assertEqual(config["speed"], expected_float)

    def test_get_voice_config_handles_invalid_string_speeds(self):
        """Test that invalid string speeds default to 1.0."""
        with self.assertLogs(
            logger=logging.getLogger("text_to_audio.services.voice_configuration"),
            level="WARNING",
        ):
            config = self.service.get_voice_config(
                detected_tone="neutral", user_preferences={"speed": "invalid"}
            )

        # Invalid speed should default to 1.0
        self.assertIsInstance(config["speed"], float)
        self.assertEqual(config["speed"], 1.0)

    def test_get_voice_config_handles_none_speed(self):
        """Test that None speed values are handled gracefully."""
        config = self.service.get_voice_config(
            detected_tone="neutral", user_preferences={"speed": None}
        )

        # None speed should use default from tone mapping
        self.assertIsInstance(config["speed"], float)
        self.assertEqual(config["speed"], 1.0)  # Default for neutral tone

    def test_get_voice_config_article_preferences_speed_conversion(self):
        """Test that article-specific speed preferences are converted."""
        config = self.service.get_voice_config(
            detected_tone="formal",
            article_preferences={"speed": "1.1"},  # String from article form
        )

        self.assertIsInstance(config["speed"], float)
        self.assertEqual(config["speed"], 1.1)

    def test_get_voice_config_voice_recommendation_speed_conversion(self):
        """Test that AI-recommended speeds are converted."""
        config = self.service.get_voice_config(
            detected_tone="formal",
            voice_recommendation={"speed": "0.9"},  # String from AI recommendation
        )

        self.assertIsInstance(config["speed"], float)
        self.assertEqual(config["speed"], 0.9)

    def test_get_voice_config_voice_preset_speed_conversion(self):
        """Test that voice preset speeds are converted."""
        # Mock voice preset with string speed
        mock_preset = Mock()
        mock_preset.voice_id = "alloy"
        mock_preset.speed = "1.25"  # String speed stored in preset

        config = self.service.get_voice_config(
            detected_tone="formal", voice_preset=mock_preset
        )

        self.assertIsInstance(config["speed"], float)
        self.assertEqual(config["speed"], 1.25)

    def test_get_voice_config_precedence_order_with_string_speeds(self):
        """Test that speed precedence works correctly with string conversions."""
        mock_preset = Mock()
        mock_preset.voice_id = "alloy"
        mock_preset.speed = "1.5"  # Lower precedence

        config = self.service.get_voice_config(
            detected_tone="formal",  # Default 1.0
            user_preferences={"speed": "1.1"},  # Lower precedence
            voice_recommendation={"speed": "1.3"},  # Lower precedence
            voice_preset=mock_preset,  # Lower precedence
            article_preferences={"speed": "1.2"},  # Highest precedence
        )

        # Should use article preference speed (highest precedence)
        self.assertIsInstance(config["speed"], float)
        self.assertEqual(config["speed"], 1.2)

    def test_get_voice_config_mixed_type_speeds(self):
        """Test handling when different sources provide different types."""
        # Mix of float, int, and string speeds
        config = self.service.get_voice_config(
            detected_tone="formal",
            user_preferences={"speed": 1.1},  # float
            article_preferences={"speed": "1.25"},  # string (highest precedence)
        )

        # Should use article preference and convert to float
        self.assertIsInstance(config["speed"], float)
        self.assertEqual(config["speed"], 1.25)

    def test_get_voice_config_preserves_other_fields(self):
        """Test that speed conversion doesn't affect other configuration fields."""
        config = self.service.get_voice_config(
            detected_tone="formal", user_preferences={"voice": "nova", "speed": "1.25"}
        )

        # Voice should be preserved
        self.assertEqual(config["voice"], "nova")
        # Speed should be converted
        self.assertIsInstance(config["speed"], float)
        self.assertEqual(config["speed"], 1.25)

    def test_get_voice_config_empty_string_speed(self):
        """Test that empty string speeds are handled gracefully."""
        # Empty strings in preferences get filtered out by the if condition
        # So they don't reach the conversion logic - this is actually correct behavior
        config = self.service.get_voice_config(
            detected_tone="neutral",
            user_preferences={"speed": ""},  # Empty string gets filtered out
        )

        # Empty string should use default from tone mapping (1.0 for neutral)
        self.assertIsInstance(config["speed"], float)
        self.assertEqual(config["speed"], 1.0)

    def test_get_voice_config_whitespace_string_speed(self):
        """Test that whitespace-only string speeds are handled gracefully."""
        # Whitespace-only strings pass the truthiness test so they reach conversion
        with self.assertLogs(
            logger=logging.getLogger("text_to_audio.services.voice_configuration"),
            level="WARNING",
        ):
            config = self.service.get_voice_config(
                detected_tone="neutral",
                user_preferences={"speed": "   "},  # Whitespace only
            )

        # Whitespace string should default to 1.0
        self.assertIsInstance(config["speed"], float)
        self.assertEqual(config["speed"], 1.0)
