"""Test dynamic token sizing fix for content analysis service."""

import json
from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings

from text_to_audio.services.content_analysis import ContentAnalysisService


@override_settings(
    OPENAI_API_KEY="test_api_key",
    MAX_ANALYSIS_WORDS=8000,
    OPENAI_ANALYSIS_MODEL="gpt-4o-mini",
)
class ContentAnalysisTokenFixTest(TestCase):
    """Test dynamic token sizing in ContentAnalysisService."""

    def setUp(self):
        """Set up test service."""
        self.service = ContentAnalysisService(openai_api_key="fake_key")
        # Mock the client property
        self.mock_client = MagicMock()
        self.service._client = self.mock_client

    def test_estimate_token_count(self):
        """Test token count estimation."""
        # Test with various text lengths
        test_cases = [
            ("Hello world", 2),  # ~11 chars / 4 = 2.75, ~2 words / 0.75 = 2.67 -> 2
            (
                "This is a longer text with multiple words",
                10,
            ),  # ~42 chars / 4 = 10.5, ~8 words / 0.75 = 10.67 -> 10
            ("A" * 400, 100),  # 400 chars / 4 = 100
            (
                "Word " * 100,
                133,
            ),  # 500 chars / 4 = 125, 100 words / 0.75 = 133.33 -> 133
        ]

        for text, expected_min in test_cases:
            result = self.service._estimate_token_count(text)
            self.assertGreaterEqual(
                result,
                expected_min,
                f"Token estimate for '{text[:20]}...' should be at least {expected_min}",
            )

    def test_calculate_dynamic_max_tokens_gpt4(self):
        """Test dynamic token calculation for GPT-4 models."""
        # Test with GPT-4 (8k context)
        prompt = "A" * 4000  # ~1000 tokens
        max_tokens = self.service._calculate_dynamic_max_tokens(prompt, "gpt-4")

        # With ~1000 prompt tokens, should have ~7000 remaining
        # 80% of 7000 = 5600, which is > 500
        self.assertGreater(max_tokens, 500)
        self.assertLess(max_tokens, 7000)

    def test_calculate_dynamic_max_tokens_gpt4o(self):
        """Test dynamic token calculation for GPT-4o models."""
        # Test with GPT-4o (128k context)
        prompt = "A" * 40000  # ~10000 tokens
        max_tokens = self.service._calculate_dynamic_max_tokens(prompt, "gpt-4o")

        # With ~10000 prompt tokens, should have ~118000 remaining
        # 80% of 118000 = 94400
        self.assertGreater(max_tokens, 90000)
        self.assertLess(max_tokens, 128000)

    def test_calculate_dynamic_max_tokens_gpt4o_mini(self):
        """Test dynamic token calculation for GPT-4o-mini models."""
        # Test with GPT-4o-mini (128k context)
        prompt = "A" * 40000  # ~10000 tokens
        max_tokens = self.service._calculate_dynamic_max_tokens(prompt, "gpt-4o-mini")

        # Similar to GPT-4o
        self.assertGreater(max_tokens, 90000)
        self.assertLess(max_tokens, 128000)

    def test_calculate_dynamic_max_tokens_minimum(self):
        """Test that we always get at least 500 tokens for completion."""
        # Test with a very long prompt that leaves little room
        prompt = "A" * 30000  # ~7500 tokens for GPT-4 (8k model)
        max_tokens = self.service._calculate_dynamic_max_tokens(prompt, "gpt-4")

        # Should still get at least 500 tokens
        self.assertGreaterEqual(max_tokens, 500)

    def test_calculate_dynamic_max_tokens_unknown_model(self):
        """Test fallback for unknown models."""
        prompt = "A" * 4000  # ~1000 tokens
        max_tokens = self.service._calculate_dynamic_max_tokens(
            prompt, "unknown-model-xyz"
        )

        # Should use default 8k limit
        # With ~1000 prompt tokens, should have ~7000 remaining
        # 80% of 7000 = 5600
        self.assertGreater(max_tokens, 500)
        self.assertLess(max_tokens, 7000)

    @patch("text_to_audio.services.content_analysis.logger")
    def test_dynamic_token_calculation_logging(self, mock_logger):
        """Test that token calculation is logged."""
        prompt = "Test prompt"
        self.service._calculate_dynamic_max_tokens(prompt, "gpt-4o-mini")

        # Check that info was logged
        mock_logger.info.assert_called_once()
        log_message = mock_logger.info.call_args[0][0]
        self.assertIn("Dynamic token calculation", log_message)
        self.assertIn("gpt-4o-mini", log_message)

    def test_analyze_content_with_dynamic_tokens(self):
        """Test analyze_content using dynamic token calculation."""
        # Mock the response
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = json.dumps(
            {
                "voices": [
                    {
                        "name": "narrator",
                        "tone": "Clear and neutral",
                        "tts_model": "alloy",
                        "tts_speed": 1.0,
                    }
                ],
                "audio_segments": [
                    {"text": "Test article content", "voice_name": "narrator"}
                ],
            }
        )

        self.mock_client.chat.completions.create.return_value = mock_response

        # Analyze content without specifying max_completion_tokens
        result = self.service.analyze_content(
            "Test article content", title="Test Title"
        )

        # Check that OpenAI was called
        self.mock_client.chat.completions.create.assert_called_once()
        call_args = self.mock_client.chat.completions.create.call_args

        # Verify dynamic max_completion_tokens was calculated (not the default 500)
        self.assertIn("max_completion_tokens", call_args.kwargs)
        self.assertNotEqual(call_args.kwargs["max_completion_tokens"], 500)

        # Verify result structure
        self.assertIn("voices", result)
        self.assertIn("audio_segments", result)

    def test_analyze_content_with_explicit_max_tokens(self):
        """Test analyze_content with explicitly specified max_completion_tokens."""
        # Mock the response
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = json.dumps(
            {
                "voices": [
                    {
                        "name": "narrator",
                        "tone": "Test",
                        "tts_model": "alloy",
                        "tts_speed": 1.0,
                    }
                ],
                "audio_segments": [{"text": "Test", "voice_name": "narrator"}],
            }
        )

        self.mock_client.chat.completions.create.return_value = mock_response

        # Analyze content with explicit max_completion_tokens
        self.service.analyze_content("Test", max_completion_tokens=1000)

        # Check that the explicit value was used
        call_args = self.mock_client.chat.completions.create.call_args
        self.assertEqual(call_args.kwargs["max_completion_tokens"], 1000)

    def test_analyze_long_content_no_truncation(self):
        """Test that long content analysis doesn't get truncated."""
        # Create a long article (8000 words)
        long_text = " ".join(["word"] * 8000)

        # Mock a long response (>500 tokens worth of JSON)
        voices = []
        segments = []
        for i in range(20):  # Create many voices and segments
            voices.append(
                {
                    "name": f"character_{i}",
                    "tone": f"This is a detailed description of character {i}'s tone and speaking style",
                    "tts_model": "alloy",
                    "tts_speed": 1.0,
                }
            )
            segments.append(
                {
                    "text": f"This is segment {i} with text that represents dialogue or narration",
                    "voice_name": f"character_{i}",
                }
            )

        large_response = {"voices": voices, "audio_segments": segments}

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = json.dumps(large_response)

        self.mock_client.chat.completions.create.return_value = mock_response

        # Analyze the long content
        result = self.service.analyze_content(long_text, title="Long Article")

        # Verify the response wasn't truncated
        self.assertEqual(len(result["voices"]), 20)
        self.assertEqual(len(result["audio_segments"]), 20)

        # Check that a large max_completion_tokens was used
        call_args = self.mock_client.chat.completions.create.call_args
        max_tokens = call_args.kwargs["max_completion_tokens"]
        # With 8000 words (~10666 tokens) and gpt-4o-mini (128k), should get much more than 500
        self.assertGreater(max_tokens, 80000)  # Should be much larger than default 500

    def test_legacy_multi_voice_with_chunks(self):
        """Test that chunked analysis works with dynamic tokens."""
        # This simulates what happens in tasks.py when article > MAX_ANALYSIS_WORDS
        chunk1 = " ".join(["word"] * 8000)  # First 8000 words
        chunk2 = " ".join(["more"] * 4000)  # Additional 4000 words

        # Mock responses for each chunk
        mock_response1 = MagicMock()
        mock_response1.choices = [MagicMock()]
        mock_response1.choices[0].message.content = json.dumps(
            {
                "voices": [
                    {
                        "name": "narrator",
                        "tone": "Professional",
                        "tts_model": "nova",
                        "tts_speed": 1.0,
                    },
                    {
                        "name": "expert",
                        "tone": "Academic",
                        "tts_model": "onyx",
                        "tts_speed": 0.9,
                    },
                ],
                "audio_segments": [
                    {"text": "First chunk content", "voice_name": "narrator"},
                    {"text": "Expert quote in first chunk", "voice_name": "expert"},
                ],
            }
        )

        mock_response2 = MagicMock()
        mock_response2.choices = [MagicMock()]
        mock_response2.choices[0].message.content = json.dumps(
            {
                "voices": [
                    {
                        "name": "narrator",
                        "tone": "Professional",
                        "tts_model": "nova",
                        "tts_speed": 1.0,
                    },
                    {
                        "name": "interviewer",
                        "tone": "Curious",
                        "tts_model": "echo",
                        "tts_speed": 1.1,
                    },
                ],
                "audio_segments": [
                    {"text": "Second chunk content", "voice_name": "narrator"},
                    {"text": "Interview question", "voice_name": "interviewer"},
                ],
            }
        )

        # Set up mock to return different responses
        self.mock_client.chat.completions.create.side_effect = [
            mock_response1,
            mock_response2,
        ]

        # Analyze both chunks
        result1 = self.service.analyze_content(chunk1, title="Article Part 1")
        result2 = self.service.analyze_content(chunk2, title="Article Part 2")

        # Both should succeed without truncation
        self.assertEqual(len(result1["voices"]), 2)
        self.assertEqual(len(result1["audio_segments"]), 2)
        self.assertEqual(len(result2["voices"]), 2)
        self.assertEqual(len(result2["audio_segments"]), 2)

        # Check that appropriate max_tokens were used for both
        calls = self.mock_client.chat.completions.create.call_args_list
        for call in calls:
            max_tokens = call.kwargs["max_completion_tokens"]
            self.assertGreater(
                max_tokens, 90000
            )  # Should be dynamically calculated for gpt-4o-mini
