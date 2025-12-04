# AIDEV-NOTE: Light TTS abstraction - facade for provider switching
"""TTS Service facade for provider abstraction.

This module provides a unified interface for TTS generation across
different providers (OpenAI, Google Cloud TTS, Gemini AI Studio).
It uses a light facade pattern to delegate to provider-specific implementations.

Provider selection:
- OpenAI: Uses OpenAI TTS API (alloy, nova, etc.)
- Google Cloud TTS: Uses Chirp3-HD, Neural2 voices (no prompt support)
- Gemini AI Studio: Uses Gemini TTS with prompt/styling support
"""

import logging
from typing import Optional

import openai

from appconfig.utils import (
    get_default_tts_provider,
    get_google_tts_voice_type,
    get_openai_api_key,
    get_openai_tts_model,
)

from .gemini_tts_provider import GeminiTTSProvider
from .google_tts_provider import GoogleTTSProvider
from text_to_audio.utils import sanitize_text_for_tts

logger = logging.getLogger(__name__)

# AIDEV-NOTE: Gemini TTS short voice names - these support prompts via AI Studio API
GEMINI_VOICE_NAMES = {
    "Achernar",
    "Aoede",
    "Autonoe",
    "Callirrhoe",
    "Despina",
    "Erinome",
    "Gacrux",
    "Kore",
    "Laomedeia",
    "Leda",
    "Pulcherrima",
    "Sulafat",
    "Vindemiatrix",
    "Zephyr",
    "Achird",
    "Algenib",
    "Algieba",
    "Alnilam",
    "Charon",
    "Enceladus",
    "Fenrir",
    "Iapetus",
    "Orus",
    "Puck",
    "Rasalgethi",
    "Sadachbia",
    "Sadaltager",
    "Schedar",
    "Umbriel",
    "Zubenelgenubi",
}


class TTSService:
    """Facade for TTS provider operations.

    Delegates to provider-specific implementations without heavy abstraction.
    Provider selection resolved at initialization.

    Example:
        # Use default provider from global config
        tts_service = TTSService()
        audio_bytes = tts_service.generate_speech(
            text="Hello world",
            voice="alloy",
            speed=1.0
        )

        # Use specific provider
        tts_service = TTSService(provider="google")
        audio_bytes = tts_service.generate_speech(
            text="Hello world",
            voice="en-US-Journey-D",
            speed=1.0
        )
    """

    def __init__(self, provider: Optional[str] = None):
        """Initialize TTS service with provider.

        Args:
            provider: "openai" or "google" (defaults to global config)
        """
        self.provider = provider or get_default_tts_provider()
        self._openai_client = None
        self._google_provider = None
        self._gemini_provider = None

        logger.debug(f"TTSService initialized with provider: {self.provider}")

    @property
    def openai_client(self):
        """Lazy-load OpenAI client."""
        if self._openai_client is None:
            api_key = get_openai_api_key()
            if not api_key:
                raise ValueError("OpenAI API key not configured")

            self._openai_client = openai.OpenAI(api_key=api_key)
            logger.debug("OpenAI client initialized")

        return self._openai_client

    @property
    def google_provider(self):
        """Lazy-load Google Cloud TTS provider (Chirp3-HD, Neural2)."""
        if self._google_provider is None:
            self._google_provider = GoogleTTSProvider()
            logger.debug("Google Cloud TTS provider initialized")

        return self._google_provider

    @property
    def gemini_provider(self):
        """Lazy-load Gemini AI Studio TTS provider (supports prompts)."""
        if self._gemini_provider is None:
            self._gemini_provider = GeminiTTSProvider()
            logger.debug("Gemini AI Studio TTS provider initialized")

        return self._gemini_provider

    def _validate_voice_for_provider(self, voice: str) -> str:
        """Validate voice is compatible with provider and return valid voice.

        Args:
            voice: Voice ID to validate

        Returns:
            Valid voice ID for the current provider
        """
        # Define OpenAI voices
        openai_voices = {
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

        # Define Google Cloud TTS voices (prefixes)
        google_cloud_voice_prefixes = (
            "en-US-Journey-",
            "en-US-Chirp3-HD-",
            "en-US-Neural2-",
        )

        voice_lower = voice.lower()
        is_openai_voice = voice_lower in openai_voices
        is_google_cloud_voice = voice.startswith(google_cloud_voice_prefixes)
        is_gemini_voice = voice in GEMINI_VOICE_NAMES

        if self.provider == "openai":
            if is_openai_voice:
                return voice
            else:
                # Using Google/Gemini voice with OpenAI - use default
                logger.warning(
                    f"Voice '{voice}' is not an OpenAI voice. Using default 'alloy'"
                )
                return "alloy"
        elif self.provider == "google":
            voice_type = get_google_tts_voice_type()
            default_voice = {
                "gemini": "Kore",  # Use Gemini short name for prompt support
                "chirp3": "en-US-Chirp3-HD-Charon",
                "neural2": "en-US-Neural2-A",
            }.get(voice_type, "Kore")

            # Check if the voice matches the configured voice type
            # AIDEV-NOTE: Journey voices are deprecated and should be remapped
            is_journey_voice = voice.startswith("en-US-Journey-")

            # Remap Journey voices to the configured voice type's default
            if is_journey_voice and voice_type in ("gemini", "chirp3"):
                logger.warning(
                    f"Journey voice '{voice}' is deprecated. "
                    f"Remapping to '{default_voice}' for voice_type '{voice_type}'"
                )
                return default_voice

            # Validate voice matches configured type
            if is_google_cloud_voice or is_gemini_voice:
                return voice
            else:
                # Using OpenAI voice with Google - use default
                logger.warning(
                    f"Voice '{voice}' is not a Google voice. "
                    f"Using default '{default_voice}' for provider 'google'"
                )
                return default_voice
        else:
            return voice

    def _is_gemini_voice(self, voice: str) -> bool:
        """Check if voice is a Gemini TTS voice (supports prompts).

        Args:
            voice: Voice name to check

        Returns:
            True if voice supports Gemini TTS with prompts
        """
        return voice in GEMINI_VOICE_NAMES

    def generate_speech(
        self,
        text: str,
        voice: str,
        speed: float = 1.0,
        model: Optional[str] = None,
        instructions: Optional[str] = None,
        response_format: str = "wav",
    ) -> bytes:
        """Generate speech audio from text.

        Args:
            text: Text to convert to speech
            voice: Voice ID (provider-specific)
            speed: Speech rate (0.25 to 4.0)
            model: TTS model (OpenAI-specific, optional)
            instructions: Optional prompt/instructions for voice style
            response_format: Audio format (wav, mp3, etc.)

        Returns:
            Audio bytes in specified format

        Raises:
            ValueError: If provider is unknown or not configured
        """
        # AIDEV-NOTE: Sanitize text to remove URLs/markdown before TTS
        # This prevents Google TTS "sentence too long" errors from URLs
        text = sanitize_text_for_tts(text)

        # Validate voice for provider (auto-map if needed)
        validated_voice = self._validate_voice_for_provider(voice)

        if self.provider == "openai":
            return self._generate_openai(
                text, validated_voice, speed, model, instructions, response_format
            )
        elif self.provider == "google":
            return self._generate_google(
                text, validated_voice, speed, instructions, response_format
            )
        else:
            raise ValueError(f"Unknown TTS provider: {self.provider}")

    def _generate_openai(
        self, text, voice, speed, model, instructions, response_format
    ) -> bytes:
        """OpenAI TTS generation.

        Args:
            text: Text to synthesize
            voice: OpenAI voice ID (alloy, nova, etc.)
            speed: Speech rate
            model: TTS model (tts-1, tts-1-hd, gpt-4o-mini-tts)
            instructions: Optional instructions for voice style
            response_format: Audio format

        Returns:
            Audio bytes
        """
        # Build request matching existing pattern
        tts_args = {
            "model": model or get_openai_tts_model(),
            "voice": voice,
            "input": text,
            "response_format": response_format,
        }

        # Add speed if not default
        if speed != 1.0:
            tts_args["speed"] = speed

        # Add instructions if provided (for certain models)
        if instructions and tts_args["model"] in ["tts-1-hd", "gpt-4o-mini-tts"]:
            tts_args["instructions"] = instructions

        logger.debug(
            f"OpenAI TTS request: model={tts_args['model']}, "
            f"voice={voice}, speed={speed}, text_length={len(text)}"
        )

        response = self.openai_client.audio.speech.create(**tts_args)

        # Read all bytes from response
        audio_bytes = b""
        for chunk in response.iter_bytes():
            audio_bytes += chunk

        logger.debug(f"OpenAI TTS generated {len(audio_bytes)} bytes")
        return audio_bytes

    def _generate_google(
        self, text, voice, speed, instructions, response_format
    ) -> bytes:
        """Google TTS generation.

        Uses Gemini AI Studio API for Gemini voices (supports prompts),
        or Google Cloud TTS API for Chirp3-HD/Neural2 voices.

        Args:
            text: Text to synthesize
            voice: Google voice name (e.g., "Kore" or "en-US-Chirp3-HD-Charon")
            speed: Speech rate
            instructions: Optional prompt for Gemini TTS styling
            response_format: Audio format

        Returns:
            Audio bytes
        """
        # AIDEV-NOTE: Use Gemini AI Studio for short voice names (supports prompts)
        # Use Google Cloud TTS for full voice names (Chirp3-HD, Neural2)
        if self._is_gemini_voice(voice):
            logger.info(
                f"Gemini AI Studio TTS request: voice={voice}, "
                f"text_length={len(text)}, has_prompt={instructions is not None}"
            )

            try:
                audio_bytes = self.gemini_provider.synthesize_speech(
                    text=text,
                    voice_name=voice,
                    prompt=instructions,
                    output_format=response_format,
                    model="flash",  # Use flash for speed
                )
                logger.info(f"Gemini AI Studio TTS generated {len(audio_bytes)} bytes")
                return audio_bytes
            except Exception as e:
                logger.warning(
                    f"Gemini AI Studio TTS failed: {e}. "
                    f"Falling back to Google Cloud TTS."
                )
                # Fall through to Google Cloud TTS

        # Use Google Cloud TTS for Chirp3-HD, Neural2, or as fallback
        logger.debug(
            f"Google Cloud TTS request: voice={voice}, speed={speed}, "
            f"text_length={len(text)}"
        )

        audio_bytes = self.google_provider.synthesize_speech(
            text=text,
            voice_name=voice,
            speed=speed,
            prompt=instructions,
            output_format=response_format,
        )

        logger.debug(f"Google Cloud TTS generated {len(audio_bytes)} bytes")
        return audio_bytes

    def get_char_limit(self) -> int:
        """Return max characters per request for this provider.

        Returns:
            Maximum character limit for single TTS request
        """
        if self.provider == "openai":
            return 4096
        elif self.provider == "google":
            return 4000  # Gemini TTS limit
        return 4000
