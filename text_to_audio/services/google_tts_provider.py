# AIDEV-NOTE: Google Cloud TTS implementation - supports Gemini TTS (with prompts), Chirp3-HD, Neural2
"""Google Cloud Text-to-Speech provider implementation.

This module provides integration with Google Cloud TTS API, supporting
multiple voice types:
- Gemini TTS: Multi-speaker, prompt-based control for styling/tone/emotion
- Chirp 3 HD: Premium quality, emotional resonance, 30 voices
- Neural2: Standard quality, cost-effective

Gemini TTS supports styling instructions via the `prompt` parameter, allowing
control over tone, emotion, accent, pace, and speaking style through natural
language instructions.
"""

import io
import logging
import wave
from typing import Dict, Optional

logger = logging.getLogger(__name__)


def _wrap_pcm_in_wav(
    pcm_data: bytes, sample_rate: int = 24000, channels: int = 1, sample_width: int = 2
) -> bytes:
    """Wrap raw PCM data (LINEAR16) in a WAV container with proper RIFF header.

    Google Cloud TTS LINEAR16 encoding returns raw PCM data without headers.
    This function adds the proper WAV/RIFF container for playback compatibility.

    Args:
        pcm_data: Raw PCM audio bytes (LINEAR16 format)
        sample_rate: Sample rate in Hz (Google TTS uses 24000 Hz)
        channels: Number of audio channels (1 for mono)
        sample_width: Bytes per sample (2 for 16-bit audio)

    Returns:
        WAV file bytes with proper RIFF header
    """
    # AIDEV-NOTE: LINEAR16 from Google TTS is 24kHz mono 16-bit signed little-endian
    wav_buffer = io.BytesIO()

    with wave.open(wav_buffer, "wb") as wav_file:
        wav_file.setnchannels(channels)
        wav_file.setsampwidth(sample_width)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(pcm_data)

    return wav_buffer.getvalue()


# AIDEV-NOTE: Gemini TTS models - use these for prompt/styling support
GEMINI_TTS_MODELS = {
    "flash": "gemini-2.5-flash-tts",  # Low-latency, cost-efficient
    "pro": "gemini-2.5-pro-tts",  # High-quality, more control
    "flash-lite": "gemini-2.5-flash-lite-preview-tts",  # Single-speaker preview
}

# AIDEV-NOTE: Gemini TTS uses short voice names (not full IDs like Chirp3-HD)
GEMINI_VOICE_NAMES = [
    # Female voices
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
    # Male voices
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
]


class GoogleTTSProvider:
    """Google Cloud Text-to-Speech provider implementation.

    Supports three voice types:
    - Gemini TTS: Multi-speaker, prompt-based control, 30 named voices
    - Chirp 3 HD: Premium quality, emotional resonance, 30 voices
    - Neural2: Standard quality, cost-effective

    Example (single speaker with styling):
        provider = GoogleTTSProvider()
        audio_bytes = provider.synthesize_speech(
            text="Hello world",
            voice_name="Charon",
            prompt="Speak in a warm, friendly tone with a slight smile"
        )

    Example (multi-speaker):
        provider = GoogleTTSProvider()
        audio_bytes = provider.synthesize_multispeaker(
            text="Alice: Hello!\\nBob: Hi there!",
            speakers={"Alice": "Kore", "Bob": "Charon"},
            prompt="A cheerful conversation between friends"
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
            from google.api_core import client_options as client_options_lib
            from google.cloud import texttospeech_v1
        except ImportError as e:
            raise ImportError(
                "Google Cloud Text-to-Speech library not installed. "
                "Install with: pip install google-cloud-texttospeech"
            ) from e

        try:
            if api_key:
                # Use API key authentication (simpler)
                logger.info("Initializing Google TTS with API key authentication")
                client_options = client_options_lib.ClientOptions(api_key=api_key)
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
                logger.info(
                    "Google TTS client initialized successfully with service account"
                )
        except Exception as e:
            raise ValueError(f"Failed to initialize Google TTS client: {e}") from e

    def synthesize_speech(
        self,
        text: str,
        voice_name: str,
        speed: float = 1.0,
        prompt: Optional[str] = None,
        output_format: str = "wav",
        model: str = "pro",
    ) -> bytes:
        """Synthesize speech using Google TTS API.

        Args:
            text: Text to synthesize (max 4000 bytes)
            voice_name: Voice name - can be:
                - Gemini short name: "Charon", "Kore"
                - Chirp3-HD full name: "en-US-Chirp3-HD-Charon"
                - Neural2 full name: "en-US-Neural2-A"
            speed: Speech rate (0.25 to 4.0)
            prompt: Optional styling instructions for Gemini TTS (max 4000 bytes)
                Examples:
                - "Speak in a calm, professional tone"
                - "Read this with excitement and energy"
                - "Narrate like a documentary"
                - "Whisper mysteriously"
            output_format: Audio format (wav, mp3, opus, pcm)
            model: Gemini model to use: "flash", "pro", or "flash-lite"

        Returns:
            Audio bytes in specified format

        Raises:
            ValueError: If voice name is invalid or request fails
        """
        from google.cloud import texttospeech_v1

        # Determine voice type from voice name
        voice_type = self._get_voice_type(voice_name)

        logger.info(
            f"Google TTS synthesis: voice={voice_name}, "
            f"type={voice_type}, speed={speed}, "
            f"text_length={len(text)}, has_prompt={prompt is not None}"
        )

        # Build synthesis input - include prompt for Gemini TTS
        if voice_type == "gemini" and prompt:
            logger.info(f"Using Gemini TTS with prompt: {prompt[:100]}...")
            synthesis_input = texttospeech_v1.SynthesisInput(text=text, prompt=prompt)
        else:
            synthesis_input = texttospeech_v1.SynthesisInput(text=text)

        # Build voice selection
        voice = self._build_voice_params(voice_name, voice_type, model)

        # Build audio config
        # Note: Gemini TTS doesn't support speaking_rate in the same way
        audio_config_params = {
            "audio_encoding": self._get_audio_encoding(output_format),
        }

        # Only add speaking_rate for non-Gemini voices
        if voice_type != "gemini":
            audio_config_params["speaking_rate"] = speed

        audio_config = texttospeech_v1.AudioConfig(**audio_config_params)

        try:
            # Call Google TTS API
            response = self.client.synthesize_speech(
                input=synthesis_input, voice=voice, audio_config=audio_config
            )

            audio_bytes = response.audio_content

            # AIDEV-NOTE: LINEAR16 returns raw PCM without WAV headers - wrap in WAV container
            # when wav format is requested to ensure proper RIFF header for ffmpeg/pydub
            if output_format.lower() == "wav":
                audio_bytes = _wrap_pcm_in_wav(audio_bytes)
                logger.debug(
                    f"Wrapped LINEAR16 data in WAV container: {len(audio_bytes)} bytes"
                )

            logger.info(f"Google TTS synthesis successful: {len(audio_bytes)} bytes")
            return audio_bytes

        except Exception as e:
            logger.error(f"Google TTS synthesis failed: {e}")
            raise ValueError(f"Google TTS synthesis failed: {e}") from e

    def synthesize_multispeaker(
        self,
        text: str,
        speakers: Dict[str, str],
        prompt: Optional[str] = None,
        output_format: str = "wav",
        model: str = "pro",
    ) -> bytes:
        """Synthesize multi-speaker dialogue using Gemini TTS.

        Args:
            text: Dialogue text with speaker labels, e.g.:
                "Alice: Hello there!
                 Bob: Hi, how are you?"
            speakers: Dict mapping speaker aliases to voice names, e.g.:
                {"Alice": "Kore", "Bob": "Charon"}
                Note: Speaker aliases must be alphanumeric (no spaces)
            prompt: Optional styling instructions for the conversation
            output_format: Audio format (wav, mp3, opus, pcm)
            model: Gemini model: "flash" or "pro" (flash-lite doesn't support multi-speaker)

        Returns:
            Audio bytes with multi-speaker dialogue

        Raises:
            ValueError: If speakers dict is invalid or request fails
        """
        from google.cloud import texttospeech_v1

        logger.info(
            f"Google TTS multi-speaker synthesis: "
            f"speakers={list(speakers.keys())}, model={model}, "
            f"text_length={len(text)}, has_prompt={prompt is not None}"
        )

        # Build synthesis input with optional prompt
        if prompt:
            synthesis_input = texttospeech_v1.SynthesisInput(text=text, prompt=prompt)
        else:
            synthesis_input = texttospeech_v1.SynthesisInput(text=text)

        # Build multi-speaker voice config
        speaker_voice_configs = []
        for alias, voice_id in speakers.items():
            # Validate alias is alphanumeric
            if not alias.replace("_", "").isalnum():
                raise ValueError(
                    f"Speaker alias '{alias}' must be alphanumeric (no spaces). "
                    "Use underscores if needed."
                )

            speaker_voice_configs.append(
                texttospeech_v1.MultispeakerPrebuiltVoice(
                    speaker_alias=alias,
                    speaker_id=voice_id,
                )
            )

        multi_speaker_voice_config = texttospeech_v1.MultiSpeakerVoiceConfig(
            speaker_voice_configs=speaker_voice_configs
        )

        # Get model name
        model_name = GEMINI_TTS_MODELS.get(model, GEMINI_TTS_MODELS["pro"])

        voice = texttospeech_v1.VoiceSelectionParams(
            language_code="en-US",
            model_name=model_name,
            multi_speaker_voice_config=multi_speaker_voice_config,
        )

        # Build audio config
        audio_config = texttospeech_v1.AudioConfig(
            audio_encoding=self._get_audio_encoding(output_format),
        )

        try:
            response = self.client.synthesize_speech(
                input=synthesis_input, voice=voice, audio_config=audio_config
            )

            audio_bytes = response.audio_content

            # AIDEV-NOTE: LINEAR16 returns raw PCM without WAV headers - wrap in WAV container
            if output_format.lower() == "wav":
                audio_bytes = _wrap_pcm_in_wav(audio_bytes)
                logger.debug(
                    f"Wrapped LINEAR16 data in WAV container: {len(audio_bytes)} bytes"
                )

            logger.info(
                f"Google TTS multi-speaker synthesis successful: {len(audio_bytes)} bytes"
            )
            return audio_bytes

        except Exception as e:
            logger.error(f"Google TTS multi-speaker synthesis failed: {e}")
            raise ValueError(f"Google TTS multi-speaker synthesis failed: {e}") from e

    def _get_voice_type(self, voice_name: str) -> str:
        """Determine voice type from voice name.

        Args:
            voice_name: Google voice name

        Returns:
            Voice type: "gemini", "chirp3", or "neural2"
        """
        voice_name_lower = voice_name.lower()

        # Check for Chirp3-HD voices (full names like "en-US-Chirp3-HD-Charon")
        if "chirp3" in voice_name_lower:
            return "chirp3"
        # Check for Neural2 voices
        elif "neural2" in voice_name_lower:
            return "neural2"
        # Check for Journey voices (legacy Gemini)
        elif "journey" in voice_name_lower:
            return "gemini"
        # Check if it's a short Gemini voice name
        elif voice_name in GEMINI_VOICE_NAMES:
            return "gemini"
        else:
            # Default to configured voice type
            from appconfig.utils import get_google_tts_voice_type

            default_type = get_google_tts_voice_type()
            logger.warning(
                f"Could not determine voice type for '{voice_name}', "
                f"defaulting to: {default_type}"
            )
            return default_type

    def _build_voice_params(self, voice_name: str, voice_type: str, model: str = "pro"):
        """Build voice selection parameters.

        Args:
            voice_name: Google voice name
            voice_type: Voice type (gemini, chirp3, neural2)
            model: Gemini model to use (for gemini voice type)

        Returns:
            VoiceSelectionParams configured for the voice
        """
        from google.cloud import texttospeech_v1

        if voice_type == "gemini":
            # Gemini TTS uses short voice names and requires model_name
            # Extract just the voice name if it's a full ID
            short_name = self._extract_short_voice_name(voice_name)
            model_name = GEMINI_TTS_MODELS.get(model, GEMINI_TTS_MODELS["pro"])

            logger.debug(f"Gemini TTS: voice={short_name}, model={model_name}")

            return texttospeech_v1.VoiceSelectionParams(
                language_code="en-US",
                name=short_name,
                model_name=model_name,
            )
        else:
            # Chirp3-HD and Neural2 use full voice names
            # Extract language code from voice name
            # e.g., "en-US-Chirp3-HD-Charon" -> "en-US"
            parts = voice_name.split("-")
            if len(parts) >= 2:
                language_code = f"{parts[0]}-{parts[1]}"
            else:
                language_code = "en-US"
                logger.warning(
                    f"Could not parse language code from '{voice_name}', "
                    f"defaulting to: {language_code}"
                )

            return texttospeech_v1.VoiceSelectionParams(
                language_code=language_code,
                name=voice_name,
            )

    def _extract_short_voice_name(self, voice_name: str) -> str:
        """Extract short voice name from full voice ID.

        Args:
            voice_name: Full or short voice name

        Returns:
            Short voice name (e.g., "Charon" from "en-US-Chirp3-HD-Charon")
        """
        # If it's already a short name, return as-is
        if voice_name in GEMINI_VOICE_NAMES:
            return voice_name

        # Try to extract from full Chirp3-HD format
        if "Chirp3-HD-" in voice_name:
            parts = voice_name.split("Chirp3-HD-")
            if len(parts) == 2:
                return parts[1]

        # Try to extract last part after splitting by dash
        parts = voice_name.split("-")
        if len(parts) > 0:
            last_part = parts[-1]
            # Check if it matches a known voice
            for known_voice in GEMINI_VOICE_NAMES:
                if known_voice.lower() == last_part.lower():
                    return known_voice

        logger.warning(
            f"Could not extract short voice name from '{voice_name}', using as-is"
        )
        return voice_name

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
