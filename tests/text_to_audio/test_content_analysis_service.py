import json
import unittest
from unittest.mock import MagicMock

# Configure Django settings before importing the service
from django.conf import settings

if not settings.configured:
    settings.configure(
        MAX_ANALYSIS_WORDS=8000,
        OPENAI_API_KEY="fake_key_from_settings",
        OPENAI_ANALYSIS_MODEL="gpt-4.1",
        OPENAI_TTS_MODEL="tts-1-hd",
        LOG_OPENAI_API_CALLS=False,  # Assuming this might be used by utils
        # Add any other settings that might be accessed at import time or runtime by the service or its utils
    )

import openai  # Import openai directly for APIError

from text_to_audio.services.content_analysis import ContentAnalysisService


class TestContentAnalysisService(unittest.TestCase):

    def setUp(self):
        # Settings are now globally configured, but we can still override for specific test scenarios if needed
        # using @override_settings from django.test if we switched to Django's TestCase,
        # or by directly modifying settings if careful. For now, global config should be fine.
        self.service = ContentAnalysisService(
            openai_api_key="fake_key_override"
        )  # Test with override
        # Mock the client property directly on the instance for focused testing
        self.mock_openai_client = MagicMock()
        self.service._client = self.mock_openai_client

    def test_successful_summary_extraction(self):
        # No need to mock settings here anymore if configured globally and not changed per test
        mock_response = MagicMock()
        mock_choice = MagicMock()
        mock_message = MagicMock()

        expected_summary = "This is a test summary."
        expected_voices = [
            {
                "name": "narrator",
                "tone": "neutral",
                "tts_model": "alloy",
                "tts_speed": 1.0,
            }
        ]
        expected_segments = [{"text": "Hello world", "voice_name": "narrator"}]

        mock_message.content = json.dumps(
            {
                "summary": expected_summary,
                "voices": expected_voices,
                "audio_segments": expected_segments,
            }
        )
        mock_choice.message = mock_message
        mock_response.choices = [mock_choice]
        mock_response.usage = MagicMock(
            prompt_tokens=10, completion_tokens=20, total_tokens=30
        )
        mock_response.id = "cmpl-test"
        mock_response.model = "gpt-4"
        mock_response.object = "chat.completion"
        mock_response.created = 1234567890

        self.mock_openai_client.chat.completions.create.return_value = mock_response

        result = self.service.analyze_content("Sample text for analysis.")

        self.assertEqual(result.get("summary"), expected_summary)
        self.assertEqual(result.get("voices"), expected_voices)
        self.assertEqual(result.get("audio_segments"), expected_segments)
        self.mock_openai_client.chat.completions.create.assert_called_once()

    def test_missing_summary_in_llm_response(self):
        mock_response = MagicMock()
        mock_choice = MagicMock()
        mock_message = MagicMock()

        expected_voices = [
            {
                "name": "narrator",
                "tone": "neutral",
                "tts_model": "alloy",
                "tts_speed": 1.0,
            }
        ]
        expected_segments = [{"text": "Hello world", "voice_name": "narrator"}]

        # Simulate LLM response without the 'summary' field
        mock_message.content = json.dumps(
            {"voices": expected_voices, "audio_segments": expected_segments}
        )
        mock_choice.message = mock_message
        mock_response.choices = [mock_choice]
        mock_response.usage = MagicMock(
            prompt_tokens=10, completion_tokens=20, total_tokens=30
        )
        mock_response.id = "cmpl-test"
        mock_response.model = "gpt-4"
        mock_response.object = "chat.completion"
        mock_response.created = 1234567890

        self.mock_openai_client.chat.completions.create.return_value = mock_response

        sample_text = "Sample text for analysis."
        result = self.service.analyze_content(sample_text)

        # Expecting a default value for summary, e.g., an empty string
        self.assertEqual(result.get("summary"), "")

        # The service's current behavior on missing keys (like 'summary' here)
        # is to raise ValueError in the try block, then the except block returns a fully default structure.
        expected_default_voices = [
            {
                "name": "narrator",
                "tone": "Neutral, standard narration",
                "tts_model": "alloy",
                "tts_speed": 1.0,
            }
        ]
        expected_default_segments = [
            {
                "text": sample_text,  # The original full text is used in fallback
                "voice_name": "narrator",
            }
        ]
        self.assertEqual(result.get("voices"), expected_default_voices)
        self.assertEqual(result.get("audio_segments"), expected_default_segments)
        self.mock_openai_client.chat.completions.create.assert_called_once()

    def test_invalid_json_response_from_llm(self):
        mock_response = MagicMock()
        mock_choice = MagicMock()
        mock_message = MagicMock()

        mock_message.content = "This is not valid JSON."  # Invalid JSON
        mock_choice.message = mock_message
        mock_response.choices = [mock_choice]
        mock_response.usage = MagicMock(
            prompt_tokens=10, completion_tokens=20, total_tokens=30
        )
        mock_response.id = "cmpl-test"
        mock_response.model = "gpt-4"
        mock_response.object = "chat.completion"
        mock_response.created = 1234567890

        self.mock_openai_client.chat.completions.create.return_value = mock_response

        sample_text = "Sample text for analysis with invalid JSON."
        result = self.service.analyze_content(sample_text)

        # Expecting the default fallback structure
        self.assertEqual(result.get("summary"), "")
        self.assertEqual(len(result.get("voices", [])), 1)
        self.assertEqual(result.get("voices")[0]["name"], "narrator")
        self.assertEqual(len(result.get("audio_segments", [])), 1)
        self.assertEqual(
            result.get("audio_segments")[0]["text"], sample_text
        )  # Original full text
        self.assertEqual(result.get("audio_segments")[0]["voice_name"], "narrator")
        self.mock_openai_client.chat.completions.create.assert_called_once()

    def test_api_error_propagated(self):
        self.mock_openai_client.chat.completions.create.side_effect = openai.APIError(
            "Test API Error", request=None, body=None
        )

        with self.assertRaises(openai.APIError):
            self.service.analyze_content("Sample text that will trigger an API error.")

        self.mock_openai_client.chat.completions.create.assert_called_once()

    def test_empty_voices_or_segments_in_llm_response(self):
        mock_response = MagicMock()
        mock_choice = MagicMock()
        mock_message = MagicMock()

        # Test case 1: Empty voices list
        mock_message.content = json.dumps(
            {
                "summary": "Summary exists",
                "voices": [],  # Empty voices
                "audio_segments": [{"text": "Segment 1", "voice_name": "narrator"}],
            }
        )
        mock_choice.message = mock_message
        mock_response.choices = [mock_choice]
        self.mock_openai_client.chat.completions.create.return_value = mock_response

        sample_text = "Sample text for empty voices test."
        result1 = self.service.analyze_content(sample_text)
        self.assertEqual(result1.get("summary"), "")  # Fallback summary
        self.assertEqual(
            result1.get("audio_segments")[0]["text"], sample_text
        )  # Fallback uses original text

        # Test case 2: Empty audio_segments list
        mock_message.content = json.dumps(
            {
                "summary": "Summary exists",
                "voices": [
                    {
                        "name": "narrator",
                        "tone": "neutral",
                        "tts_model": "alloy",
                        "tts_speed": 1.0,
                    }
                ],
                "audio_segments": [],  # Empty segments
            }
        )
        # No need to re-assign mock_choice.message and mock_response.choices if they are the same objects
        self.mock_openai_client.chat.completions.create.return_value = (
            mock_response  # Re-assign if changed
        )

        sample_text_2 = "Sample text for empty segments test."
        result2 = self.service.analyze_content(sample_text_2)
        self.assertEqual(result2.get("summary"), "")  # Fallback summary
        self.assertEqual(
            result2.get("audio_segments")[0]["text"], sample_text_2
        )  # Fallback uses original text

        # Reset call count for the next part if needed or make separate tests
        # self.mock_openai_client.chat.completions.create.reset_mock()


if __name__ == "__main__":
    unittest.main()
