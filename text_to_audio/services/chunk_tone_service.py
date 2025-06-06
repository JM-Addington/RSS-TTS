"""
ChunkToneService for LLM-driven text chunking and tone analysis.
"""

import json
import logging
import time
from typing import Optional

import openai
from django.conf import settings
from pydantic import ValidationError

from text_to_audio.schemas.chunk_tone import ChunkData, ChunkTonePayload, TTSVoice

logger = logging.getLogger(__name__)


def _is_mock_object(obj):
    """Check if an object is a mock (for testing)."""
    return obj is not None and hasattr(obj, "_mock_name")


class ChunkToneService:
    """Service for LLM-driven text chunking and tone analysis."""

    def __init__(self, openai_api_key: Optional[str] = None):
        """Initialize with optional OpenAI API key override."""
        self.openai_api_key = openai_api_key
        self._client: Optional[openai.OpenAI] = None

    @property
    def client(self):
        """Lazily initialize OpenAI client."""
        if self._client is None:
            self._client = openai.OpenAI(
                api_key=self.openai_api_key or settings.OPENAI_API_KEY
            )
        return self._client

    def get_payload(self, text: str, title: str, max_chars: int) -> ChunkTonePayload:
        """
        Generate ChunkTonePayload using LLM analysis.

        Args:
            text: The text content to analyze and chunk
            title: The article title for context
            max_chars: Maximum characters per chunk

        Returns:
            ChunkTonePayload with analyzed chunks and voice assignments
        """
        prompt = self._build_prompt(text, title, max_chars)

        # First attempt
        try:
            response_json = self._call_openai(prompt)
            return ChunkTonePayload.model_validate(response_json)
        except (ValidationError, Exception) as e:
            logger.warning(f"First attempt failed: OpenAI API error: {e}")

            # Retry attempt
            try:
                response_json = self._call_openai(prompt)
                return ChunkTonePayload.model_validate(response_json)
            except (ValidationError, Exception) as e2:
                logger.error(
                    f"Second attempt failed: OpenAI API error: {e2}. Using fallback."
                )
                return self.create_fallback_payload(text)

    def get_single_voice_payload(
        self,
        text: str,
        title: str,
        max_chars: int,
        voice: str,
        character_name: str = "narrator",
    ) -> ChunkTonePayload:
        """
        Generate ChunkTonePayload for single-voice mode with text normalization.

        This is used when a user has selected a voice preset - we disable multi-voice
        and only use their chosen voice, but still chunk intelligently and normalize
        text for better TTS output.

        Args:
            text: The text content to analyze and chunk
            title: The article title for context
            max_chars: Maximum characters per chunk
            voice: The voice to use for all chunks
            character_name: The character name to use (default: "narrator")

        Returns:
            ChunkTonePayload with all chunks using the same voice
        """
        prompt = self._build_single_voice_prompt(text, title, max_chars, voice)

        # First attempt
        try:
            response_json = self._call_openai(prompt)
            # Override any voice assignments from LLM with the preset voice
            if "chunks" in response_json:
                for chunk in response_json["chunks"]:
                    chunk["voice"] = {"voice": voice}
                    chunk["character_name"] = character_name
            return ChunkTonePayload.model_validate(response_json)
        except (ValidationError, Exception) as e:
            logger.warning(f"First attempt failed for single-voice mode: {e}")

            # Retry attempt
            try:
                response_json = self._call_openai(prompt)
                # Override any voice assignments from LLM with the preset voice
                if "chunks" in response_json:
                    for chunk in response_json["chunks"]:
                        chunk["voice"] = {"voice": voice}
                        chunk["character_name"] = character_name
                return ChunkTonePayload.model_validate(response_json)
            except (ValidationError, Exception) as e2:
                logger.error(
                    f"Second attempt failed for single-voice mode: {e2}. Using fallback."
                )
                return self.create_single_voice_fallback(text, voice)

    def create_single_voice_fallback(self, text: str, voice: str) -> ChunkTonePayload:
        """
        Create a fallback payload with specified voice when LLM processing fails.

        Args:
            text: The text content to create fallback for
            voice: The voice to use

        Returns:
            ChunkTonePayload with single specified voice
        """
        return ChunkTonePayload(
            chunks=[
                ChunkData(
                    text=text,
                    voice=TTSVoice(voice=voice),
                    character_name="narrator",
                    instructions="Speak in a clear, engaging manner with appropriate expression for the content.",
                )
            ]
        )

    def create_fallback_payload(self, text: str) -> ChunkTonePayload:
        """
        Create a fallback payload with narrator voice when LLM processing fails.

        Args:
            text: The text content to create fallback for

        Returns:
            ChunkTonePayload with single narrator voice
        """
        return ChunkTonePayload(
            chunks=[
                ChunkData(
                    text=text,
                    voice=TTSVoice(voice="alloy"),
                    character_name="narrator",
                    instructions="Speak in a clear, engaging manner with appropriate expression for the content.",
                )
            ]
        )

    def _build_prompt(self, text: str, title: str, max_chars: int) -> str:
        """Build the prompt for the LLM."""
        return f"""You are a text-to-speech specialist. Analyze the following article and break it into \
logical chunks for multi-voice narration.

Article Title: {title}

Article Text:
{text}

Requirements:
1. Break the text into logical chunks (maximum {max_chars} characters each)
2. Assign appropriate voices and character names for different speakers/narrators
3. Use these available voices: alloy, echo, fable, onyx, nova, shimmer
4. For narrative text, use character_name "narrator"
5. For dialogue or quotes, use appropriate character names
6. Provide detailed TTS instructions for each chunk to guide tone, pacing, and delivery style

Return ONLY a JSON object with this exact structure:
{{
  "chunks": [
    {{
      "text": "chunk text here",
      "voice": {{"voice": "voice_name"}},
      "character_name": "narrator_or_character_name",
      "instructions": "Detailed TTS instructions describing affect, tone, pacing, pitch variation, and speaking style for this specific chunk"
    }}
  ]
}}

Example instructions:
- "Speak with enthusiasm and energy. Use an upbeat tone with varied pitch. Moderate pace for clarity."
- "Use a calm, authoritative tone. Steady pace with clear enunciation. Professional news delivery style."
- "Convey emotion and intimacy. Slower pace with gentle inflection. Personal storytelling style."
- "Use dramatic emphasis. Varied pacing to build tension. Dynamic pitch variation for engagement."

The JSON must be valid and parseable. Do not include any other text or explanations."""

    def _build_single_voice_prompt(
        self, text: str, title: str, max_chars: int, voice: str
    ) -> str:
        """Build the prompt for single-voice mode with text normalization."""
        return f"""You are a text-to-speech preprocessing specialist. Prepare the following article for TTS by:

1. Breaking it into logical chunks (maximum {max_chars} characters each)
2. Expanding ALL abbreviations for natural speech
3. Converting dates and numbers to spoken form
4. Maintaining the original meaning while optimizing for speech

Article Title: {title}

Article Text:
{text}

Text Normalization Rules:
- Expand state abbreviations: VA → Virginia, CA → California, NY → New York, etc.
- Expand titles: Mr. → Mister, Mrs. → Missus, Dr. → Doctor, Prof. → Professor, etc.
- Expand common abbreviations: St. → Street, Ave. → Avenue, Co. → Company, Inc. → Incorporated, etc.
- Convert dates: 1/1/2000 → January first, two thousand; 12/25/2025 → December twenty-fifth, twenty twenty-five
- Convert times: 3:30 PM → three thirty P M, 9:00 AM → nine o'clock A M
- Spell out numbers in context: "5 people" → "five people", "$100" → "one hundred dollars"
- Expand units: kg → kilograms, mi → miles, ft → feet, etc.
- Handle special cases: U.S. → United States, U.K. → United Kingdom, E.U. → European Union

Return ONLY a JSON object with this exact structure:
{{
  "chunks": [
    {{
      "text": "normalized chunk text here with all abbreviations expanded",
      "voice": {{"voice": "{voice}"}},
      "character_name": "narrator",
      "instructions": "Detailed TTS instructions for tone and pacing"
    }}
  ]
}}

IMPORTANT: All chunks must use voice "{voice}" and character_name "narrator".
The text in each chunk should have ALL abbreviations and numbers expanded for natural speech.
Break at natural pauses like paragraphs or sentence boundaries when possible."""

    def _call_openai(self, prompt: str) -> dict:
        """
        Call OpenAI API and return parsed JSON response.

        Args:
            prompt: The prompt to send to OpenAI

        Returns:
            Parsed JSON response as dict

        Raises:
            ValidationError: If response cannot be parsed or validated
        """
        model = getattr(settings, "OPENAI_ANALYSIS_MODEL", "gpt-4.1")

        # Prepare request data for logging
        request_data = {
            "model": model,
            "messages": [
                {
                    "role": "system",
                    "content": "You are a professional text-to-speech specialist. Return only valid JSON.",
                },
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.3,
            "max_tokens": 4000,
        }

        # Log ChunkToneService API call details
        logger.info(
            f"ChunkToneService API Call: model={model}, "
            f"max_tokens=4000, temperature=0.3, "
            f"prompt_length={len(prompt)} chars"
        )

        # Call OpenAI API with detailed logging
        start_time = time.monotonic()
        try:
            response = self.client.chat.completions.create(**request_data)
            end_time = time.monotonic()
            duration_ms = int((end_time - start_time) * 1000)

            # Extract response data for logging
            response_data = {
                "id": response.id,
                "model": response.model,
                "object": response.object,
                "created": response.created,
                "choices": [
                    {
                        "index": choice.index,
                        "message": {
                            "role": choice.message.role,
                            "content": choice.message.content,
                        },
                        "finish_reason": choice.finish_reason,
                    }
                    for choice in response.choices
                ],
                "usage": (
                    {
                        "prompt_tokens": response.usage.prompt_tokens,
                        "completion_tokens": response.usage.completion_tokens,
                        "total_tokens": response.usage.total_tokens,
                    }
                    if response.usage
                    else None
                ),
            }

            # Log successful API call
            from ..utils import log_openai_api_call

            log_openai_api_call(
                operation="Chunk Tone Analysis",
                request_data=request_data,
                response_data=response_data,
                duration_ms=duration_ms,
            )

            response_text = response.choices[0].message.content.strip()

            # Parse JSON response
            try:
                return json.loads(response_text)
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse JSON response: {e}")
                logger.debug(f"Raw response: {response_text}")
                raise Exception(f"Invalid JSON response: {e}") from e

        except Exception as e:
            end_time = time.monotonic()
            duration_ms = int((end_time - start_time) * 1000)

            # Log failed API call
            from ..utils import log_openai_api_call

            log_openai_api_call(
                operation="Chunk Tone Analysis",
                request_data=request_data,
                error=e,
                duration_ms=duration_ms,
            )

            logger.error(f"OpenAI API call failed: {e}")
            raise Exception(f"OpenAI API error: {e}") from e
