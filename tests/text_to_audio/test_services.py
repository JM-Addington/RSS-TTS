import json
from unittest.mock import MagicMock, patch

from django.conf import settings
from django.test import TestCase

from tests.helpers import make_chat_completion
from text_to_audio.services.content_analysis import ContentAnalysisService

# Ensure settings are configured if not already
if not settings.configured:
    settings.configure(
        OPENAI_API_KEY="test_api_key",  # Dummy key for tests
        # Add other necessary settings if ContentAnalysisService depends on them
    )


class ContentAnalysisServiceTest(TestCase):
    def setUp(self):
        self.service = ContentAnalysisService(openai_api_key="fake_key")
        # Mock the client property directly on the instance for consistent mocking
        self.mock_openai_client = MagicMock()
        self.service._client = self.mock_openai_client

    @patch("text_to_audio.services.content_analysis.json.loads")
    def test_analyze_content_valid_multi_voice_json(self, mock_json_loads):
        """Test with valid multi-voice JSON output from LLM."""
        sample_text = "This is a test text."
        mock_llm_response_content = {
            "summary": "This is a test summary with multiple voices.",
            "voices": [
                {
                    "name": "narrator",
                    "tone": "neutral",
                    "tts_model": "alloy",
                    "tts_speed": 1.0,
                },
                {
                    "name": "character1",
                    "tone": "excited",
                    "tts_model": "nova",
                    "tts_speed": 1.2,
                },
            ],
            "audio_segments": [
                {"text": "Segment 1.", "voice_name": "narrator"},
                {"text": "Segment 2!", "voice_name": "character1"},
            ],
        }
        # json.loads should return the dict directly in this case
        mock_json_loads.return_value = mock_llm_response_content

        # Mock the API call structure
        json_content = json.dumps(mock_llm_response_content)

        mock_message = MagicMock()
        mock_message.content = json_content

        mock_choice = MagicMock()
        mock_choice.message = mock_message

        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        self.mock_openai_client.chat.completions.create.return_value = mock_response

        # We need json.loads to return the actual dict when the service calls it
        # Just handle the expected case and let others fail if unexpected
        expected_json_string = json.dumps(mock_llm_response_content)

        def side_effect_json_loads(s):
            if s == expected_json_string:
                return mock_llm_response_content
            # For other cases, let's try to parse manually or raise
            raise ValueError(f"Unexpected json.loads call with: {s[:100]}...")

        mock_json_loads.side_effect = side_effect_json_loads
        result = self.service.analyze_content(sample_text)

        self.assertEqual(result, mock_llm_response_content)
        self.assertEqual(result["voices"][0]["tts_model"], "alloy")
        self.assertEqual(result["voices"][0]["tts_speed"], 1.0)
        self.assertEqual(result["voices"][1]["tts_model"], "nova")
        self.assertEqual(result["voices"][1]["tts_speed"], 1.2)
        self.mock_openai_client.chat.completions.create.assert_called_once()

    def test_analyze_content_malformed_json(self):
        """Test with malformed JSON output from LLM."""
        sample_text = "Another test text."
        malformed_json_string = (
            '{"voices": [{"name": "narrator"} /* missing comma */ "audio_segments": []}'
        )

        mock_message = MagicMock()
        mock_message.content = malformed_json_string
        mock_choice = MagicMock()
        mock_choice.message = mock_message
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        self.mock_openai_client.chat.completions.create.return_value = (
            make_chat_completion(malformed_json_string)
        )

        result = self.service.analyze_content(sample_text)

        self.assertIn("voices", result)
        self.assertEqual(len(result["voices"]), 1)
        self.assertEqual(result["voices"][0]["name"], "narrator")
        self.assertEqual(result["voices"][0]["tts_model"], "alloy")  # Default
        self.assertIn("audio_segments", result)
        self.assertEqual(len(result["audio_segments"]), 1)
        self.assertEqual(result["audio_segments"][0]["text"], sample_text)
        self.assertEqual(result["audio_segments"][0]["voice_name"], "narrator")

    def test_analyze_content_llm_returns_non_json_text(self):
        """Test when LLM returns plain text instead of JSON."""
        sample_text = "A third test text."
        non_json_response = "This is not JSON, just plain text."

        mock_message = MagicMock()
        mock_message.content = non_json_response
        mock_choice = MagicMock()
        mock_choice.message = mock_message
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        self.mock_openai_client.chat.completions.create.return_value = (
            make_chat_completion(non_json_response)
        )

        result = self.service.analyze_content(sample_text)

        self.assertEqual(result["voices"][0]["name"], "narrator")
        self.assertEqual(result["audio_segments"][0]["text"], sample_text)

    def test_analyze_content_empty_voices_list(self):
        """Test LLM returning JSON with empty 'voices' list."""
        sample_text = "Text for empty voices test."
        llm_response_content = {
            "voices": [],  # Empty list
            "audio_segments": [{"text": "Segment 1.", "voice_name": "narrator"}],
        }

        mock_completion_message = MagicMock()
        mock_completion_message.message.content = json.dumps(llm_response_content)
        mock_choice = MagicMock()
        mock_choice.message = mock_completion_message
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        self.mock_openai_client.chat.completions.create.return_value = mock_response

        # Mock json.loads for this specific case
        with patch(
            "text_to_audio.services.content_analysis.json.loads",
            return_value=llm_response_content,
        ):
            result = self.service.analyze_content(sample_text)

        self.assertEqual(result["voices"][0]["name"], "narrator")  # Default fallback
        self.assertEqual(result["audio_segments"][0]["text"], sample_text)

    def test_analyze_content_empty_audio_segments_list(self):
        """Test LLM returning JSON with empty 'audio_segments' list."""
        sample_text = "Text for empty segments test."
        llm_response_content = {
            "voices": [
                {
                    "name": "narrator",
                    "tone": "neutral",
                    "tts_model": "alloy",
                    "tts_speed": 1.0,
                }
            ],
            "audio_segments": [],  # Empty list
        }
        mock_completion_message = MagicMock()
        mock_completion_message.message.content = json.dumps(llm_response_content)
        mock_choice = MagicMock()
        mock_choice.message = mock_completion_message
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        self.mock_openai_client.chat.completions.create.return_value = mock_response

        # Mock json.loads for this specific case
        with patch(
            "text_to_audio.services.content_analysis.json.loads",
            return_value=llm_response_content,
        ):
            result = self.service.analyze_content(sample_text)

        self.assertEqual(result["voices"][0]["name"], "narrator")  # Default fallback
        self.assertEqual(result["audio_segments"][0]["text"], sample_text)
