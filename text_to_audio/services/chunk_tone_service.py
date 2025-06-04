"""
ChunkToneService for LLM-driven text chunking and tone analysis.
"""

import json
import logging
import time
from typing import Optional

from django.conf import settings

import openai
from pydantic import ValidationError

from text_to_audio.schemas.chunk_tone import ChunkData, ChunkTonePayload, TTSVoice
from text_to_audio.tts_utils import _legacy_chunk_text

logger = logging.getLogger(__name__)


def _is_mock_object(obj):
    """Check if an object is a mock (for testing)."""
    return obj is not None and hasattr(obj, "_mock_name")


class ChunkToneService:
    """Service for LLM-driven text chunking and tone analysis."""

    # Conservative token limits for different models
    MODEL_TOKEN_LIMITS = {
        "gpt-4.1": 128000,  # Conservative estimate for GPT-4 family
        "gpt-4o-mini": 128000,
        "gpt-4o": 128000,
        "gpt-4": 8000,
        "gpt-3.5-turbo": 4000,
    }

    # Reserve tokens for response and system messages
    RESPONSE_TOKEN_RESERVE = 4500  # max_tokens=4000 + system prompt + formatting

    # Maximum reasonable text length for analysis (in words) - now uses Django setting

    def __init__(self, openai_api_key: Optional[str] = None, usage_logger=None):
        """Initialize with optional OpenAI API key override and usage logger."""
        self.openai_api_key = openai_api_key
        self._client: Optional[openai.OpenAI] = None
        self.usage_logger = usage_logger

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

        Raises:
            ValueError: If the text is too large for analysis
        """
        # Check if text is too large for analysis
        word_count = len(text.split())
        max_analysis_words = getattr(settings, "MAX_ANALYSIS_WORDS", 8000)
        if word_count > max_analysis_words:
            logger.warning(
                f"Text too large for ChunkToneService analysis ({word_count:,} words > {max_analysis_words:,} limit). "
                f"Using fallback chunking."
            )
            return self.create_fallback_payload(text)

        # Build prompt and check token limits
        prompt = self._build_prompt(text, title, max_chars)

        # Estimate token count and validate against model limits
        model = getattr(settings, "OPENAI_CHUNK_TONE_MODEL", "gpt-4.1")
        estimated_tokens = self._estimate_token_count(prompt)
        max_tokens = self.MODEL_TOKEN_LIMITS.get(model, 8000)  # Conservative default

        if estimated_tokens + self.RESPONSE_TOKEN_RESERVE > max_tokens:
            logger.error(
                f"Prompt too large for model {model}: {estimated_tokens:,} estimated tokens + {self.RESPONSE_TOKEN_RESERVE:,} reserve > {max_tokens:,} limit. "
                f"Text length: {len(text):,} chars, {word_count:,} words. Using fallback chunking."
            )
            return self.create_fallback_payload(text)

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

    def create_fallback_payload(self, text: str) -> ChunkTonePayload:
        """
        Create a fallback payload with narrator voice when LLM processing fails.

        For very long texts, this creates multiple chunks using simple text splitting.

        Args:
            text: The text content to create fallback for

        Returns:
            ChunkTonePayload with narrator voice chunks
        """
        # For very long texts, split into manageable chunks
        max_chunk_chars = 4000  # Default chunk size
        chunks = []

        if len(text) <= max_chunk_chars:
            # Single chunk for short text
            chunks = [
                ChunkData(
                    text=text,
                    voice=TTSVoice(voice="alloy"),
                    character_name="narrator",
                    instructions="Speak in a clear, engaging manner with appropriate expression for the content.",
                )
            ]
        else:
            # Split long text into chunks using sophisticated sentence-aware splitting
            _, text_chunks = _legacy_chunk_text(text, max_chunk_chars)
            for chunk_text in text_chunks:
                chunks.append(
                    ChunkData(
                        text=chunk_text,
                        voice=TTSVoice(voice="alloy"),
                        character_name="narrator",
                        instructions="Speak in a clear, engaging manner with appropriate expression for the content.",
                    )
                )

        return ChunkTonePayload(chunks=chunks)

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
        model = getattr(settings, "OPENAI_CHUNK_TONE_MODEL", "gpt-4.1")

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

            # Log usage statistics if usage logger is available
            if self.usage_logger and response.usage:
                tokens_used = response.usage.total_tokens
                input_tokens = getattr(response.usage, "prompt_tokens", None)
                output_tokens = getattr(response.usage, "completion_tokens", None)
                # Estimate word count from prompt (conservative estimate)
                word_count = len(prompt.split())
                self.usage_logger.log_llm_usage(
                    operation="Text Analysis",
                    tokens_used=tokens_used,
                    processing_time_ms=duration_ms,
                    word_count=word_count,
                    model_name=model,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
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

    def _estimate_token_count(self, text: str) -> int:
        """
        Estimate token count for a text string.

        Uses a conservative approximation of ~4 characters per token,
        which works reasonably well for English text.

        Args:
            text: The text to estimate tokens for

        Returns:
            Estimated token count
        """
        # Conservative estimate: ~4 characters per token for English text
        return len(text) // 4
