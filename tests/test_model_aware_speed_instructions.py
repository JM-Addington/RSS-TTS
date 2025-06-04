"""Tests for model-aware speed and instructions logic.

This module tests the critical bug fix for instructions parameter being properly
sent to all gpt-4o* models but never to tts-1* models.
"""

from unittest import TestCase

from text_to_audio.tts_utils import _configure_model_aware_speed


class ModelAwareSpeedInstructionsTests(TestCase):
    """Test model-aware speed configuration and instructions handling."""

    def test_gpt_4o_mini_tts_uses_instructions_for_speed(self):
        """Test that gpt-4o-mini-tts uses instructions for speed control."""
        updates, instructions = _configure_model_aware_speed(
            tts_model="gpt-4o-mini-tts", speed=1.25, instructions="Use a calm tone."
        )

        # Should not include speed in updates
        self.assertEqual(updates, {})
        # Should include speed instruction
        self.assertIn("Speak at 1.25x speed", instructions)
        self.assertIn("Use a calm tone", instructions)

    def test_gpt_4o_models_use_instructions_for_speed(self):
        """Test that all gpt-4o* models use instructions for speed control."""
        test_models = [
            "gpt-4o-mini-tts",
            "gpt-4o-tts",
            "gpt-4o-audio",
            "gpt-4o-v2-tts",
            "gpt-4o-enhanced",
        ]

        for model in test_models:
            with self.subTest(model=model):
                updates, instructions = _configure_model_aware_speed(
                    tts_model=model, speed=1.1, instructions=""
                )

                # Should not include speed in updates for gpt-4o models
                self.assertEqual(updates, {})
                # Should include speed instruction
                self.assertEqual(instructions, "Speak at 1.1x speed.")

    def test_tts_1_models_use_speed_parameter(self):
        """Test that tts-1 models use direct speed parameter."""
        test_models = ["tts-1", "tts-1-hd"]

        for model in test_models:
            with self.subTest(model=model):
                updates, instructions = _configure_model_aware_speed(
                    tts_model=model, speed=1.3, instructions="Use a professional tone."
                )

                # Should include speed in updates for tts-1 models
                self.assertEqual(updates, {"speed": 1.3})
                # Should preserve original instructions unchanged
                self.assertEqual(instructions, "Use a professional tone.")

    def test_speed_clamping_works_for_all_models(self):
        """Test that speed is clamped to valid range for all models."""
        test_cases = [
            ("gpt-4o-mini-tts", 0.1, 0.25),  # Below minimum
            ("gpt-4o-mini-tts", 5.0, 4.0),  # Above maximum
            ("tts-1", 0.1, 0.25),  # Below minimum
            ("tts-1", 5.0, 4.0),  # Above maximum
        ]

        for model, input_speed, expected_speed in test_cases:
            with self.subTest(model=model, input_speed=input_speed):
                updates, instructions = _configure_model_aware_speed(
                    tts_model=model, speed=input_speed, instructions=""
                )

                if model.startswith("gpt-4o"):
                    # Check clamped speed in instructions
                    self.assertIn(f"Speak at {expected_speed}x speed", instructions)
                else:
                    # Check clamped speed in updates
                    self.assertEqual(updates["speed"], expected_speed)

    def test_empty_instructions_handled_correctly(self):
        """Test behavior when no instructions are provided."""
        # gpt-4o model with no instructions
        updates, instructions = _configure_model_aware_speed(
            tts_model="gpt-4o-mini-tts", speed=1.0, instructions=""
        )

        self.assertEqual(updates, {})
        self.assertEqual(instructions, "Speak at 1.0x speed.")

        # tts-1 model with no instructions
        updates, instructions = _configure_model_aware_speed(
            tts_model="tts-1", speed=1.0, instructions=""
        )

        self.assertEqual(updates, {"speed": 1.0})
        self.assertEqual(instructions, "")

    def test_instruction_concatenation_for_gpt_4o(self):
        """Test that speed instructions are properly concatenated with existing instructions."""
        updates, instructions = _configure_model_aware_speed(
            tts_model="gpt-4o-mini-tts",
            speed=0.9,
            instructions="Speak with a dramatic flair. Use pauses for emphasis.",
        )

        self.assertEqual(updates, {})
        expected = (
            "Speak with a dramatic flair. Use pauses for emphasis. Speak at 0.9x speed."
        )
        self.assertEqual(instructions, expected)

    def test_future_gpt_4o_variants_supported(self):
        """Test that future gpt-4o variants are handled correctly."""
        future_models = [
            "gpt-4o-v3-tts",
            "gpt-4o-ultra-tts",
            "gpt-4o-premium",
            "gpt-4o-nano-tts",
        ]

        for model in future_models:
            with self.subTest(model=model):
                updates, instructions = _configure_model_aware_speed(
                    tts_model=model, speed=1.2, instructions="Test instruction."
                )

                # Should use instructions for speed (not speed parameter)
                self.assertEqual(updates, {})
                self.assertIn("Speak at 1.2x speed", instructions)
                self.assertIn("Test instruction", instructions)

    def test_non_openai_models_use_speed_parameter(self):
        """Test that non-OpenAI models use speed parameter like tts-1."""
        other_models = [
            "eleven-labs-model",
            "azure-tts",
            "google-tts",
            "custom-tts-model",
        ]

        for model in other_models:
            with self.subTest(model=model):
                updates, instructions = _configure_model_aware_speed(
                    tts_model=model, speed=1.4, instructions="Original instruction."
                )

                # Should use speed parameter (like tts-1 models)
                self.assertEqual(updates, {"speed": 1.4})
                # Should preserve original instructions
                self.assertEqual(instructions, "Original instruction.")

    def test_edge_case_model_names(self):
        """Test edge cases in model name handling."""
        edge_cases = [
            ("GPT-4O-MINI-TTS", False),  # Uppercase should not match (case-sensitive)
            ("pre-gpt-4o-suffix", False),  # Prefix shouldn't match
            ("gpt-4o", True),  # Base gpt-4o should match
            ("gpt-4", False),  # Partial match shouldn't work
            ("", False),  # Empty string
        ]

        for model, should_use_instructions in edge_cases:
            with self.subTest(model=model):
                updates, instructions = _configure_model_aware_speed(
                    tts_model=model, speed=1.0, instructions=""
                )

                if should_use_instructions:
                    # Should use instructions for speed
                    self.assertEqual(updates, {})
                    self.assertIn("Speak at 1.0x speed", instructions)
                else:
                    # Should use speed parameter
                    self.assertEqual(updates, {"speed": 1.0})
                    self.assertEqual(instructions, "")
