# AIDEV-NOTE: Light TTS abstraction - facade for provider switching
"""TTS Service facade for provider abstraction.

This module provides a unified interface for TTS generation across
different providers (OpenAI, Google). It uses a light facade pattern
to delegate to provider-specific implementations.
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)


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
        from appconfig.utils import get_default_tts_provider

        self.provider = provider or get_default_tts_provider()
        self._openai_client = None
        self._google_provider = None

        logger.debug(f"TTSService initialized with provider: {self.provider}")

    @property
    def openai_client(self):
        """Lazy-load OpenAI client."""
        if self._openai_client is None:
            import openai
            from appconfig.utils import get_openai_api_key

            api_key = get_openai_api_key()
            if not api_key:
                raise ValueError("OpenAI API key not configured")

            self._openai_client = openai.OpenAI(api_key=api_key)
            logger.debug("OpenAI client initialized")

        return self._openai_client

    @property
    def google_provider(self):
        """Lazy-load Google provider."""
        if self._google_provider is None:
            from .google_tts_provider import GoogleTTSProvider

            self._google_provider = GoogleTTSProvider()
            logger.debug("Google TTS provider initialized")

        return self._google_provider

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
        if self.provider == "openai":
            return self._generate_openai(
                text, voice, speed, model, instructions, response_format
            )
        elif self.provider == "google":
            return self._generate_google(
                text, voice, speed, instructions, response_format
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
        from appconfig.utils import get_openai_tts_model

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

        Args:
            text: Text to synthesize
            voice: Google voice name (e.g., "en-US-Journey-D")
            speed: Speech rate
            instructions: Optional prompt for Gemini TTS
            response_format: Audio format

        Returns:
            Audio bytes
        """
        logger.debug(
            f"Google TTS request: voice={voice}, speed={speed}, "
            f"text_length={len(text)}"
        )

        audio_bytes = self.google_provider.synthesize_speech(
            text=text,
            voice_name=voice,
            speed=speed,
            prompt=instructions,
            output_format=response_format,
        )

        logger.debug(f"Google TTS generated {len(audio_bytes)} bytes")
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
