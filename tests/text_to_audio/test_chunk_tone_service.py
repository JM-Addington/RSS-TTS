"""
Tests for ChunkToneService.
"""

import json
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from text_to_audio.schemas.chunk_tone import ChunkData, ChunkTonePayload, TTSVoice
from text_to_audio.services.chunk_tone_service import ChunkToneService


class TestChunkToneService:
    """Test cases for ChunkToneService."""

    @pytest.fixture
    def service(self):
        """Create ChunkToneService instance for testing."""
        return ChunkToneService(openai_api_key="test-key")

    @pytest.fixture
    def sample_text(self):
        """Sample text for testing."""
        return "Once upon a time, there was a brave knight. 'I shall save the kingdom!' he declared."

    @pytest.fixture
    def valid_response_data(self):
        """Valid LLM response data."""
        return {
            "chunks": [
                {
                    "text": "Once upon a time, there was a brave knight.",
                    "voice": {"voice": "alloy"},
                    "character_name": "narrator",
                    "instructions": "Use a calm, storytelling tone. Moderate pace with clear enunciation.",
                },
                {
                    "text": "I shall save the kingdom!",
                    "voice": {"voice": "onyx"},
                    "character_name": "knight",
                    "instructions": "Speak with determination and heroic energy.",
                },
            ]
        }

    @pytest.fixture
    def invalid_response_data(self):
        """Invalid LLM response data."""
        return {
            "chunks": [
                {
                    "text": "Some text",
                    "voice": "invalid_structure",  # Wrong structure - should be {"voice": "name"}
                    "character_name": "narrator",
                    "instructions": "Some instructions",
                }
            ]
        }

    @pytest.mark.parametrize("valid_first_try", [True, False])
    def test_get_payload_valid_json_first_try(
        self, service, sample_text, valid_response_data, monkeypatch, valid_first_try
    ):
        """Test successful processing on first attempt."""
        # Mock OpenAI client
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices[0].message.content = json.dumps(valid_response_data)
        mock_client.chat.completions.create.return_value = mock_response

        # Patch the client property
        monkeypatch.setattr(service, "_client", mock_client)

        # Call the service (pass provider to avoid DB call)
        result = service.get_payload(sample_text, "Test Title", 100, provider="openai")

        # Verify result
        assert isinstance(result, ChunkTonePayload)
        assert len(result.chunks) == 2
        assert result.chunks[0].text == "Once upon a time, there was a brave knight."
        assert result.chunks[0].voice.voice == "alloy"
        assert result.chunks[0].character_name == "narrator"
        assert "storytelling tone" in result.chunks[0].instructions
        assert result.chunks[1].text == "I shall save the kingdom!"
        assert result.chunks[1].voice.voice == "onyx"
        assert result.chunks[1].character_name == "knight"
        assert "determination" in result.chunks[1].instructions

        # Verify API was called once
        assert mock_client.chat.completions.create.call_count == 1

    def test_get_payload_invalid_then_valid_retry(
        self,
        service,
        sample_text,
        valid_response_data,
        invalid_response_data,
        monkeypatch,
    ):
        """Test retry mechanism when first response is invalid."""
        # Mock OpenAI client
        mock_client = MagicMock()
        mock_response_invalid = MagicMock()
        mock_response_invalid.choices[0].message.content = json.dumps(
            invalid_response_data
        )

        mock_response_valid = MagicMock()
        mock_response_valid.choices[0].message.content = json.dumps(valid_response_data)

        # First call returns invalid, second call returns valid
        mock_client.chat.completions.create.side_effect = [
            mock_response_invalid,
            mock_response_valid,
        ]

        # Patch the client property
        monkeypatch.setattr(service, "_client", mock_client)

        # Call the service (pass provider to avoid DB call)
        result = service.get_payload(sample_text, "Test Title", 100, provider="openai")

        # Verify result is valid (from second attempt)
        assert isinstance(result, ChunkTonePayload)
        assert len(result.chunks) == 2
        assert result.chunks[0].voice.voice == "alloy"

        # Verify API was called twice
        assert mock_client.chat.completions.create.call_count == 2

    def test_get_payload_invalid_twice_fallback(
        self, service, sample_text, invalid_response_data, monkeypatch
    ):
        """Test fallback when both attempts return invalid data."""
        # Mock OpenAI client
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices[0].message.content = json.dumps(invalid_response_data)

        # Both calls return invalid data
        mock_client.chat.completions.create.return_value = mock_response

        # Patch the client property
        monkeypatch.setattr(service, "_client", mock_client)

        # Call the service (pass provider to avoid DB call)
        result = service.get_payload(sample_text, "Test Title", 100, provider="openai")

        # Verify fallback result
        assert isinstance(result, ChunkTonePayload)
        assert len(result.chunks) == 1
        assert result.chunks[0].text == sample_text
        assert result.chunks[0].voice.voice == "alloy"
        assert result.chunks[0].character_name == "narrator"
        assert "clear, engaging manner" in result.chunks[0].instructions

        # Verify API was called twice
        assert mock_client.chat.completions.create.call_count == 2

    def test_get_payload_openai_api_error_fallback(
        self, service, sample_text, monkeypatch
    ):
        """Test fallback when OpenAI API raises an exception."""
        # Mock OpenAI client to raise an exception
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = Exception("API Error")

        # Patch the client property
        monkeypatch.setattr(service, "_client", mock_client)

        # Call the service (pass provider to avoid DB call)
        result = service.get_payload(sample_text, "Test Title", 100, provider="openai")

        # Verify fallback result
        assert isinstance(result, ChunkTonePayload)
        assert len(result.chunks) == 1
        assert result.chunks[0].text == sample_text
        assert result.chunks[0].voice.voice == "alloy"
        assert result.chunks[0].character_name == "narrator"
        assert "clear, engaging manner" in result.chunks[0].instructions

    def test_get_payload_invalid_json_fallback(self, service, sample_text, monkeypatch):
        """Test fallback when OpenAI returns invalid JSON."""
        # Mock OpenAI client
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices[0].message.content = "{ invalid json }"

        # Both calls return invalid JSON
        mock_client.chat.completions.create.return_value = mock_response

        # Patch the client property
        monkeypatch.setattr(service, "_client", mock_client)

        # Call the service (pass provider to avoid DB call)
        result = service.get_payload(sample_text, "Test Title", 100, provider="openai")

        # Verify fallback result
        assert isinstance(result, ChunkTonePayload)
        assert len(result.chunks) == 1
        assert result.chunks[0].text == sample_text
        assert result.chunks[0].voice.voice == "alloy"
        assert result.chunks[0].character_name == "narrator"
        assert "clear, engaging manner" in result.chunks[0].instructions

    def test_create_fallback_payload(self, service):
        """Test create_fallback_payload method."""
        text = "Test fallback text"
        result = service.create_fallback_payload(text)

        assert isinstance(result, ChunkTonePayload)
        assert len(result.chunks) == 1
        assert result.chunks[0].text == text
        assert result.chunks[0].voice.voice == "alloy"
        assert result.chunks[0].character_name == "narrator"
        assert "clear, engaging manner" in result.chunks[0].instructions

    def test_build_prompt(self, service):
        """Test prompt building."""
        text = "Sample text"
        title = "Sample Title"
        max_chars = 1000

        prompt = service._build_prompt(text, title, max_chars)

        assert "Sample text" in prompt
        assert "Sample Title" in prompt
        assert "1000" in prompt
        assert "JSON" in prompt
        assert "chunks" in prompt
        assert "instructions" in prompt
        assert "tone, pacing, and delivery style" in prompt

    def test_voice_validation(self):
        """Test TTSVoice validation."""
        # Valid standard voices
        valid_voice = TTSVoice(voice="alloy")
        assert valid_voice.voice == "alloy"

        # Test voice mapping for logical names
        narrator_voice = TTSVoice(voice="narrator")
        assert narrator_voice.voice == "nova"  # Maps to nova

        expert_voice = TTSVoice(voice="expert")
        assert expert_voice.voice == "echo"  # Maps to echo

        # Test fallback behavior for unrecognized voices
        unrecognized_voice = TTSVoice(voice="test_voice")
        assert unrecognized_voice.voice == "nova"  # Falls back to nova

        unrecognized_voice_with_hyphen = TTSVoice(voice="test-voice")
        assert unrecognized_voice_with_hyphen.voice == "nova"  # Falls back to nova

        # Test that all voices eventually resolve to valid OpenAI voices
        invalid_chars_voice = TTSVoice(voice="invalid@voice")
        assert invalid_chars_voice.voice == "nova"  # Falls back to nova

    def test_chunk_data_validation(self):
        """Test ChunkData validation."""
        valid_chunk = ChunkData(
            text="Test text",
            voice=TTSVoice(voice="alloy"),
            character_name="narrator",
            instructions="Speak clearly and calmly.",
        )
        assert valid_chunk.text == "Test text"
        assert valid_chunk.character_name == "narrator"
        assert valid_chunk.instructions == "Speak clearly and calmly."

        # character_name and instructions are optional
        chunk_without_optional = ChunkData(
            text="Test text", voice=TTSVoice(voice="alloy")
        )
        assert chunk_without_optional.character_name is None
        assert chunk_without_optional.instructions is None

    def test_chunk_tone_payload_validation(self):
        """Test ChunkTonePayload validation."""
        valid_chunks = [
            ChunkData(text="Text 1", voice=TTSVoice(voice="alloy")),
            ChunkData(text="Text 2", voice=TTSVoice(voice="onyx")),
        ]

        payload = ChunkTonePayload(chunks=valid_chunks)
        assert len(payload.chunks) == 2

        # Empty chunks should fail validation
        with pytest.raises(ValidationError):
            ChunkTonePayload(chunks=[])

    def test_single_voice_prompt_respects_letter_abbreviations(self, service):
        """Ensure single-voice prompt keeps letter-by-letter abbreviations."""
        prompt = service._build_single_voice_prompt("Text", "Title", 1000, "alloy")
        assert "spoken as words" in prompt
        assert "letter by letter" in prompt
