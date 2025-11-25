# AIDEV-NOTE: Google Cloud TTS implementation - supports Gemini, Chirp3, Neural2
"""Google Cloud Text-to-Speech provider implementation.

This module provides integration with Google Cloud TTS API, supporting
multiple voice types:
- Gemini TTS: Multi-speaker, prompt-based control, 28 named voices
- Chirp 3: HD: Premium quality, emotional resonance, 50+ languages
- Neural2: Standard quality, cost-effective
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)


class GoogleTTSProvider:
    """Google Cloud Text-to-Speech provider implementation.

    Supports three voice types:
    - Gemini TTS: Multi-speaker, prompt-based control, 28 named voices
    - Chirp 3: HD: Premium quality, emotional resonance, 50+ languages
    - Neural2: Standard quality, cost-effective

    Example:
        provider = GoogleTTSProvider()
        audio_bytes = provider.synthesize_speech(
            text="Hello world",
            voice_name="en-US-Journey-D",
            speed=1.0
        )
    """

    def __init__(self):
        """Initialize Google TTS client with credentials or API key.

        Supports two authentication methods:
        1. API Key (simpler, recommended for testing)
        2. Service Account JSON (more secure, recommended for production)

        Raises:
            ValueError: If Google TTS credentials are not configured
            ImportError: If Google Cloud TTS library is not installed
        """
        from appconfig.utils import get_google_tts_api_key, get_google_tts_credentials

        # Try API key first (simpler authentication)
        api_key = get_google_tts_api_key()
        credentials_data = get_google_tts_credentials()

        if not api_key and not credentials_data:
            raise ValueError(
                "Google TTS credentials not configured. "
                "Please set API key or credentials in Admin > Global Configuration "
                "or GOOGLE_TTS_API_KEY / GOOGLE_TTS_CREDENTIALS_JSON environment variables."
            )

        # Initialize Google TTS client
        try:
            from google.cloud import texttospeech_v1
            from google.api_core import client_options as client_options_lib
        except ImportError as e:
            raise ImportError(
                "Google Cloud Text-to-Speech library not installed. "
                "Install with: pip install google-cloud-texttospeech"
            ) from e

        try:
            if api_key:
                # Use API key authentication (simpler)
                logger.info("Initializing Google TTS with API key authentication")
                client_options = client_options_lib.ClientOptions(
                    api_key=api_key
                )
                self.client = texttospeech_v1.TextToSpeechClient(
                    client_options=client_options
                )
                logger.info("Google TTS client initialized successfully with API key")
            else:
                # Use service account authentication (more secure)
                from google.oauth2 import service_account

                logger.info("Initializing Google TTS with service account credentials")

                # Parse credentials if string
                if isinstance(credentials_data, str):
                    import json
                    try:
                        credentials_data = json.loads(credentials_data)
                    except json.JSONDecodeError as e:
                        raise ValueError(
                            f"Invalid Google TTS credentials JSON: {e}"
                        ) from e

                credentials = service_account.Credentials.from_service_account_info(
                    credentials_data
                )
                self.client = texttospeech_v1.TextToSpeechClient(
                    credentials=credentials
                )
                logger.info("Google TTS client initialized successfully with service account")
        except Exception as e:
            raise ValueError(
                f"Failed to initialize Google TTS client: {e}"
            ) from e

    def synthesize_speech(
        self,
        text: str,
        voice_name: str,
        speed: float = 1.0,
        prompt: Optional[str] = None,
        output_format: str = "wav",
    ) -> bytes:
        """Synthesize speech using Google TTS API.

        Args:
            text: Text to synthesize
            voice_name: Google voice name (e.g., "en-US-Journey-D")
            speed: Speech rate (0.25 to 4.0)
            prompt: Optional prompt for Gemini TTS
            output_format: Audio format (wav, mp3, opus, pcm)

        Returns:
            Audio bytes in specified format

        Raises:
            ValueError: If voice name is invalid or request fails
        """
        from google.cloud import texttospeech_v1

        # Determine voice type from voice name
        voice_type = self._get_voice_type(voice_name)

        logger.debug(
            f"Google TTS synthesis: voice={voice_name}, "
            f"type={voice_type}, speed={speed}, "
            f"text_length={len(text)}, has_prompt={prompt is not None}"
        )

        # Build synthesis input
        synthesis_input = texttospeech_v1.SynthesisInput(text=text)

        # Build voice selection
        voice = self._build_voice_params(voice_name, voice_type, prompt)

        # Build audio config
        audio_config = texttospeech_v1.AudioConfig(
            audio_encoding=self._get_audio_encoding(output_format),
            speaking_rate=speed,
        )

        try:
            # Call Google TTS API
            response = self.client.synthesize_speech(
                input=synthesis_input, voice=voice, audio_config=audio_config
            )

            audio_bytes = response.audio_content
            logger.debug(
                f"Google TTS synthesis successful: {len(audio_bytes)} bytes"
            )
            return audio_bytes

        except Exception as e:
            logger.error(f"Google TTS synthesis failed: {e}")
            raise ValueError(f"Google TTS synthesis failed: {e}") from e

    def _get_voice_type(self, voice_name: str) -> str:
        """Determine voice type from voice name.

        Args:
            voice_name: Google voice name

        Returns:
            Voice type: "gemini", "chirp3", or "neural2"
        """
        voice_name_lower = voice_name.lower()

        if "journey" in voice_name_lower or "gemini" in voice_name_lower:
            return "gemini"
        elif "chirp3" in voice_name_lower:
            return "chirp3"
        elif "neural2" in voice_name_lower:
            return "neural2"
        else:
            # Default to gemini for best quality
            from appconfig.utils import get_google_tts_voice_type

            default_type = get_google_tts_voice_type()
            logger.warning(
                f"Could not determine voice type for '{voice_name}', "
                f"defaulting to: {default_type}"
            )
            return default_type

    def _build_voice_params(self, voice_name, voice_type, prompt):
        """Build voice selection parameters.

        Args:
            voice_name: Google voice name
            voice_type: Voice type (gemini, chirp3, neural2)
            prompt: Optional prompt for Gemini TTS

        Returns:
            VoiceSelectionParams configured for the voice
        """
        from google.cloud import texttospeech_v1

        # Extract language code from voice name
        # e.g., "en-US-Journey-D" -> "en-US"
        # e.g., "en-US-Chirp3-HD-Charon" -> "en-US"
        # e.g., "en-US-Neural2-A" -> "en-US"
        parts = voice_name.split("-")
        if len(parts) >= 2:
            language_code = f"{parts[0]}-{parts[1]}"
        else:
            language_code = "en-US"  # Default fallback
            logger.warning(
                f"Could not parse language code from '{voice_name}', "
                f"defaulting to: {language_code}"
            )

        voice_params = texttospeech_v1.VoiceSelectionParams(
            language_code=language_code,
            name=voice_name,
        )

        # Add prompt for Gemini TTS if provided
        # Note: This API may vary - check latest Google TTS docs
        if voice_type == "gemini" and prompt:
            # Gemini TTS supports prompt-based control
            # The exact API for this feature should be verified with
            # Google's latest documentation
            logger.info(
                f"Gemini TTS prompt provided (length: {len(prompt)}), "
                "but prompt API integration not yet implemented"
            )
            # TODO: Implement Gemini TTS prompt API when available
            # voice_params.custom_voice = texttospeech_v1.CustomVoiceParams(
            #     model="gemini-tts",
            #     prompt=prompt
            # )

        return voice_params

    def _get_audio_encoding(self, format: str):
        """Map format string to Google audio encoding enum.

        Args:
            format: Audio format string (wav, mp3, opus, pcm)

        Returns:
            AudioEncoding enum value
        """
        from google.cloud import texttospeech_v1

        format_map = {
            "mp3": texttospeech_v1.AudioEncoding.MP3,
            "wav": texttospeech_v1.AudioEncoding.LINEAR16,
            "opus": texttospeech_v1.AudioEncoding.OGG_OPUS,
            "pcm": texttospeech_v1.AudioEncoding.LINEAR16,
        }

        encoding = format_map.get(
            format.lower(), texttospeech_v1.AudioEncoding.LINEAR16
        )

        if format.lower() not in format_map:
            logger.warning(
                f"Unknown audio format '{format}', defaulting to LINEAR16 (wav)"
            )

        return encoding
