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

# AIDEV-NOTE: Provider-specific voices for ChunkTone multi-voice mode
# OpenAI voices support full expressive range with instructions
OPENAI_VOICES = ["alloy", "echo", "fable", "onyx", "nova", "shimmer"]

# Gemini voices (AI Studio) - all 30 voices that support prompts
# Source: https://cloud.google.com/text-to-speech/docs/chirp3-hd
GEMINI_VOICES = [
    # Female voices
    "Aoede",
    "Kore",
    "Leda",
    "Zephyr",
    "Callirrhoe",
    "Despina",
    "Erinome",
    "Laomedeia",
    "Pulcherrima",
    "Sulafat",
    "Vindemiatrix",
    "Achird",
    "Algenib",
    # Male voices
    "Charon",
    "Fenrir",
    "Puck",
    "Achernar",
    "Alnilam",
    "Autonoe",
    "Enceladus",
    "Gacrux",
    "Iapetus",
    "Orus",
    "Rasalgethi",
    "Sadachbia",
    "Sadaltager",
    "Schedar",
    "Umbriel",
    "Zubenelgenubi",
]

# Default voice mappings by provider
DEFAULT_VOICE_BY_PROVIDER = {
    "openai": "alloy",
    "google": "Aoede",  # Clear, conversational, good for general narration
}


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
            from appconfig.utils import get_openai_api_key

            self._client = openai.OpenAI(
                api_key=self.openai_api_key or get_openai_api_key()
            )
        return self._client

    def get_payload(
        self,
        text: str,
        title: str,
        max_chars: int,
        fallback_voice: str = "alloy",
        provider: Optional[str] = None,
    ) -> ChunkTonePayload:
        """
        Generate ChunkTonePayload using LLM analysis.

        Args:
            text: The text content to analyze and chunk
            title: The article title for context
            max_chars: Maximum characters per chunk
            fallback_voice: Voice to use if LLM analysis fails
            provider: TTS provider ("openai" or "google") for voice selection

        Returns:
            ChunkTonePayload with analyzed chunks and voice assignments
        """
        # Resolve provider from config if not specified
        if provider is None:
            from appconfig.utils import get_default_tts_provider

            provider = get_default_tts_provider()

        prompt = self._build_prompt(text, title, max_chars, provider)

        # Determine appropriate fallback voice for provider
        effective_fallback = fallback_voice
        if provider == "google" and fallback_voice in OPENAI_VOICES:
            effective_fallback = DEFAULT_VOICE_BY_PROVIDER.get("google", "Kore")
        elif provider == "openai" and fallback_voice in GEMINI_VOICES:
            effective_fallback = DEFAULT_VOICE_BY_PROVIDER.get("openai", "alloy")

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
                return self.create_fallback_payload(text, effective_fallback)

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

    def create_fallback_payload(
        self, text: str, voice: str = "alloy"
    ) -> ChunkTonePayload:
        """
        Create a fallback payload with narrator voice when LLM processing fails.

        Args:
            text: The text content to create fallback for
            voice: The voice to use for the fallback

        Returns:
            ChunkTonePayload with single narrator voice
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

    def _build_prompt(
        self, text: str, title: str, max_chars: int, provider: str = "openai"
    ) -> str:
        """Build the prompt for the LLM.

        Args:
            text: Article text content
            title: Article title
            max_chars: Maximum characters per chunk
            provider: TTS provider ("openai" or "google") for voice selection
        """
        # Select voices based on provider with descriptions
        if provider == "google":
            voice_descriptions = """
FEMALE VOICES:
- Aoede: Clear, conversational, mid-range, thoughtful and engaging - best for podcasts, e-learning, informative content
- Kore: Energetic, youthful, mid-to-high pitch, confident and enthusiastic - best for upbeat commercials, tutorials
- Leda: Composed, professional, mid-pitch with authority and calm - best for corporate training, serious narration
- Zephyr: Energetic, bright, mid-range, perky and enthusiastic - best for upbeat commercials, children's content
- Callirrhoe: Confident, clear, mid-range, professional and articulate - best for business presentations, IVR
- Despina: Warm, inviting, mid-range, friendly and trustworthy - best for lifestyle commercials, customer service
- Erinome: Professional, articulate, lower mid-range, sophisticated - best for educational content, museum guides
- Laomedeia: Clear, conversational, mid-range, inquisitive and engaging - best for e-learning, explainer videos
- Pulcherrima: Bright, energetic, mid-to-high, youthful and upbeat - best for commercials, animation
- Sulafat: Warm, confident, mid-range, persuasive and articulate - best for corporate narration, marketing
- Vindemiatrix: Calm, thoughtful, mid-to-low, mature and composed - best for meditation, reflective content
- Achird: Youthful, mid-to-high, slightly breathy and inquisitive - best for e-learning, app tutorials
- Algenib: Warm, confident, mid-range, friendly authority - best for corporate presentations, documentaries

MALE VOICES:
- Charon: Smooth, conversational, mid-to-low, assured and trustworthy - best for podcasts, explainer videos
- Fenrir: Friendly, clear, mid-range, conversational and approachable - best for explainers, e-learning
- Puck: Clear, direct, mid-range, confident "guy next door" feel - best for how-to videos, product demos
- Achernar: Clear, mid-range, friendly and engaging - best for explainer videos, podcast intros
- Alnilam: Energetic, mid-to-low, excited and direct - best for commercials, promotional material
- Autonoe: Mature, deeper, resonant and thoughtful - best for documentaries, audiobooks (serious)
- Enceladus: Energetic, enthusiastic, mid-range, high-energy - best for promos, event announcements
- Gacrux: Smooth, confident, mid-to-low, authoritative yet approachable - best for documentaries, corporate
- Iapetus: Friendly, mid-pitch, casual "everyman" quality - best for informal tutorials, vlogs
- Orus: Mature, deep, resonant, calming and authoritative - best for documentaries, audiobooks
- Rasalgethi: Conversational, mid-range, slightly inquisitive - best for podcast discussions, quirky characters
- Sadachbia: Deeper with slight rasp, confident "cool" authority - best for movie trailers, edgy commercials
- Sadaltager: Friendly, enthusiastic, mid-range, professional - best for presentations, webinars
- Schedar: Friendly, mid-pitch, informal and down-to-earth - best for casual tutorials, vlogs
- Umbriel: Smooth, mid-to-low, authoritative yet friendly - best for documentaries, audiobooks
- Zubenelgenubi: Deep, resonant, strong authority - best for movie trailers (epic), formal announcements"""
        else:
            voice_descriptions = """
- alloy: balanced, neutral voice - versatile for general narration
- echo: warm, conversational male voice - good for friendly, approachable content
- fable: expressive, storytelling voice - good for narrative and dramatic content
- onyx: deep, authoritative male voice - good for serious topics and formal content
- nova: warm, friendly female voice - good for conversational and upbeat content
- shimmer: clear, upbeat female voice - good for energetic and positive content"""

        return f"""You are a text-to-speech specialist. Analyze the following article and break it into logical chunks for multi-voice narration.

Article Title: {title}

Article Text:
{text}

=== CHUNKING RULES ===

Break the text into logical chunks (maximum {max_chars} characters each).

CRITICAL: Keep sentences together when they form a continuous thought:
- Quoted speech stays with its attribution
- Parenthetical remarks stay with their parent sentence
- Only split when the thought clearly changes (new topic, new speaker, paragraph break)

<examples>
<example>
<input>A person with knowledge of the matter said, "the president is considering a new direction."</input>
<correct>A person with knowledge of the matter said, "the president is considering a new direction."</correct>
<incorrect_split>
Chunk 1: A person with knowledge of the matter said,
Chunk 2: "the president is considering a new direction."
</incorrect_split>
</example>

<example>
<input>Raccoons are known for their love of trash (although they aren't the only ones, as evidenced by the stories of black bears around Gatlinburg).</input>
<correct>Raccoons are known for their love of trash (although they aren't the only ones, as evidenced by the stories of black bears around Gatlinburg).</correct>
<incorrect_split>
Chunk 1: Raccoons are known for their love of trash
Chunk 2: (although they aren't the only ones, as evidenced by the stories of black bears around Gatlinburg).
</incorrect_split>
</example>

<example>
<input>The CEO announced, "We're expanding to Europe," and the crowd erupted in applause.</input>
<correct>The CEO announced, "We're expanding to Europe," and the crowd erupted in applause.</correct>
<incorrect_split>
Chunk 1: The CEO announced, "We're expanding to Europe,"
Chunk 2: and the crowd erupted in applause.
</incorrect_split>
</example>
</examples>

=== TEXT NORMALIZATION RULES ===

Abbreviations WITHOUT periods:
- US government (not U.S. government)
- UK economy (not U.K. economy)
- EU regulations (not E.U. regulations)

Abbreviations that stay as letters (spoken letter-by-letter):
- AI, GPT, CPU, FBI, CIA, NASA, CEO, CFO stay as-is

<examples>
<example>
<input>The U.S. government announced new E.U. trade talks.</input>
<output>The US government announced new EU trade talks.</output>
</example>

<example>
<input>Dr. Smith from the U.K. met with CEO Johnson.</input>
<output>Doctor Smith from the UK met with CEO Johnson.</output>
</example>
</examples>

=== VOICE ASSIGNMENT ===

Available voices:
{voice_descriptions}

Guidelines:
- For narrative text, use character_name "narrator"
- For dialogue or quotes, use appropriate character names
- Provide detailed TTS instructions for each chunk

=== OUTPUT FORMAT ===

Return ONLY a JSON object:
{{
  "chunks": [
    {{
      "text": "chunk text here",
      "voice": {{"voice": "voice_name"}},
      "character_name": "narrator_or_character_name",
      "instructions": "Detailed TTS instructions describing affect, tone, pacing, pitch variation, and speaking style"
    }}
  ]
}}

<examples>
<example>
<instructions>"Speak with enthusiasm and energy. Use an upbeat tone with varied pitch. Moderate pace for clarity."</instructions>
</example>
<example>
<instructions>"Use a calm, authoritative tone. Steady pace with clear enunciation. Professional news delivery style."</instructions>
</example>
<example>
<instructions>"Convey emotion and intimacy. Slower pace with gentle inflection. Personal storytelling style."</instructions>
</example>
</examples>

The JSON must be valid and parseable. Do not include any other text or explanations."""

    def _build_single_voice_prompt(
        self, text: str, title: str, max_chars: int, voice: str
    ) -> str:
        """Build the prompt for single-voice mode with text normalization."""
        return f"""You are a text-to-speech preprocessing specialist. Prepare the following article for TTS.

Article Title: {title}

Article Text:
{text}

=== CHUNKING RULES ===

Break the text into logical chunks (maximum {max_chars} characters each).

CRITICAL: Keep sentences together when they form a continuous thought:
- Quoted speech stays with its attribution
- Parenthetical remarks stay with their parent sentence
- Only split when the thought clearly changes (new topic, new speaker, paragraph break)

<examples>
<example>
<input>A person with knowledge of the matter said, "the president is considering a new direction."</input>
<correct>A person with knowledge of the matter said, "the president is considering a new direction."</correct>
<incorrect_split>
Chunk 1: A person with knowledge of the matter said,
Chunk 2: "the president is considering a new direction."
</incorrect_split>
</example>

<example>
<input>Raccoons are known for their love of trash (although they aren't the only ones, as evidenced by the stories of black bears around Gatlinburg).</input>
<correct>Raccoons are known for their love of trash (although they aren't the only ones, as evidenced by the stories of black bears around Gatlinburg).</correct>
<incorrect_split>
Chunk 1: Raccoons are known for their love of trash
Chunk 2: (although they aren't the only ones, as evidenced by the stories of black bears around Gatlinburg).
</incorrect_split>
</example>

<example>
<input>The CEO announced, "We're expanding to Europe," and the crowd erupted in applause.</input>
<correct>The CEO announced, "We're expanding to Europe," and the crowd erupted in applause.</correct>
<incorrect_split>
Chunk 1: The CEO announced, "We're expanding to Europe,"
Chunk 2: and the crowd erupted in applause.
</incorrect_split>
</example>
</examples>

=== TEXT NORMALIZATION RULES ===

Abbreviations WITHOUT periods (spoken as single words or expanded):
- US government (not U.S. government)
- UK economy (not U.K. economy)
- EU regulations (not E.U. regulations)
- Expand state abbreviations: VA → Virginia, CA → California, NY → New York
- Expand titles: Mr → Mister, Mrs → Missus, Dr → Doctor, Prof → Professor
- Expand street terms: St → Street, Ave → Avenue, Blvd → Boulevard

<examples>
<example>
<input>The U.S. government announced new E.U. trade talks.</input>
<output>The US government announced new EU trade talks.</output>
</example>

<example>
<input>Dr. Smith from the U.K. met with Mr. Johnson.</input>
<output>Doctor Smith from the UK met with Mister Johnson.</output>
</example>

<example>
<input>She lives at 123 Main St., Washington, D.C.</input>
<output>She lives at one twenty-three Main Street, Washington, DC.</output>
</example>
</examples>

Abbreviations that stay as letters (spoken letter-by-letter):
- AI, GPT, CPU, FBI, CIA, NASA, CEO, CFO stay as-is
- These are pronounced as individual letters, not words

Numbers and dates:
- Spell out numbers in context: "5 people" → "five people", "$100" → "one hundred dollars"
- Convert dates: 1/1/2000 → January first, two thousand
- Convert times: 3:30 PM → three thirty PM, 9:00 AM → nine AM

Do not use Markdown formatting in the final text.

=== OUTPUT FORMAT ===

Return ONLY a JSON object:
{{
  "chunks": [
    {{
      "text": "normalized chunk text here",
      "voice": {{"voice": "{voice}"}},
      "character_name": "narrator",
      "instructions": "Detailed TTS instructions for tone and pacing"
    }}
  ]
}}

All chunks must use voice "{voice}" and character_name "narrator"."""

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
            "max_tokens": 12000,
        }

        # Log ChunkToneService API call details
        logger.info(
            f"ChunkToneService API Call: model={model}, "
            f"max_tokens=12000, temperature=0.3, "
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
