# AIDEV-NOTE: Gemini AI Studio TTS - supports prompts/styling, multi-speaker, uses google-genai SDK
"""Gemini TTS provider using Google AI Studio API.

This provider uses the Google AI Studio (Gemini) API for text-to-speech,
which supports:
- Prompt-based styling instructions for tone, emotion, accent, pace
- Multi-speaker dialogue generation
- Natural language control over speech delivery

Requires: GEMINI_API_KEY environment variable or configured in admin.

Different from GoogleTTSProvider which uses Cloud TTS API:
- Gemini API: Simpler API key auth, supports prompts/styling
- Cloud TTS API: More voices, but Gemini TTS requires Vertex AI permissions
"""

import base64
import logging
from typing import Dict, Optional

logger = logging.getLogger(__name__)

# Available Gemini TTS models
GEMINI_TTS_MODELS = {
    "flash": "gemini-2.5-flash-preview-tts",
    "pro": "gemini-2.5-pro-preview-tts",
}

# Voice names (same 30 voices as Chirp3-HD)
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


class GeminiTTSProvider:
    """Gemini TTS provider using Google AI Studio API.

    This provider supports prompt-based styling and multi-speaker dialogue.

    Example (single speaker with styling):
        provider = GeminiTTSProvider()
        audio_bytes = provider.synthesize_speech(
            text="Hello world",
            voice_name="Kore",
            prompt="Speak in a warm, friendly tone"
        )

    Example (multi-speaker):
        provider = GeminiTTSProvider()
        audio_bytes = provider.synthesize_multispeaker(
            text="Speaker1: Hello!\\nSpeaker2: Hi there!",
            speakers={"Speaker1": "Kore", "Speaker2": "Charon"},
            prompt="A cheerful conversation"
        )
    """

    def __init__(self, api_key: Optional[str] = None):
        """Initialize Gemini TTS client.

        Args:
            api_key: Optional Gemini API key. If not provided, looks for
                GEMINI_API_KEY in environment or admin config.

        Raises:
            ValueError: If API key is not configured
            ImportError: If google-genai library is not installed
        """
        import os

        # Get API key from parameter, env, or config
        # Check both GEMINI_API_KEY and GOOGLE_TTS_API_KEY (AI Studio key works for both)
        self.api_key = (
            api_key or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_TTS_API_KEY")
        )

        if not self.api_key:
            # Try to get from Django config if available
            try:
                from appconfig.models import GlobalConfig

                config = GlobalConfig.objects.first()
                if (
                    config
                    and hasattr(config, "gemini_api_key")
                    and config.gemini_api_key
                ):
                    self.api_key = config.gemini_api_key
            except Exception:
                pass

        if not self.api_key:
            raise ValueError(
                "Gemini API key not configured. "
                "Set GEMINI_API_KEY environment variable or configure in admin."
            )

        # Initialize the genai client
        try:
            from google import genai

            self.genai = genai
            self.client = genai.Client(api_key=self.api_key)
            logger.info("Gemini TTS client initialized successfully")
        except ImportError as e:
            raise ImportError(
                "google-genai library not installed. "
                "Install with: pip install google-genai"
            ) from e

    def synthesize_speech(
        self,
        text: str,
        voice_name: str = "Kore",
        prompt: Optional[str] = None,
        output_format: str = "wav",
        model: str = "flash",
    ) -> bytes:
        """Synthesize speech using Gemini TTS API.

        Args:
            text: Text to synthesize
            voice_name: Voice name (e.g., "Kore", "Charon")
            prompt: Optional styling instructions like:
                - "Speak in a calm, professional tone"
                - "Read this with excitement and energy"
                - "Narrate like a documentary"
                - "Whisper mysteriously"
            output_format: Audio format (wav or mp3) - Note: API returns WAV
            model: Model to use: "flash" (faster) or "pro" (higher quality)

        Returns:
            Audio bytes (WAV format)

        Raises:
            ValueError: If synthesis fails
        """
        from google.genai import types

        model_name = GEMINI_TTS_MODELS.get(model, GEMINI_TTS_MODELS["flash"])

        # Build the content - include prompt as part of the text if provided
        if prompt:
            content = f"{prompt}: {text}"
            logger.info(f"Gemini TTS synthesis with prompt: {prompt[:50]}...")
        else:
            content = text

        logger.info(
            f"Gemini TTS synthesis: voice={voice_name}, model={model_name}, "
            f"text_length={len(text)}"
        )

        try:
            response = self.client.models.generate_content(
                model=model_name,
                contents=content,
                config=types.GenerateContentConfig(
                    response_modalities=["AUDIO"],
                    speech_config=types.SpeechConfig(
                        voice_config=types.VoiceConfig(
                            prebuilt_voice_config=types.PrebuiltVoiceConfig(
                                voice_name=voice_name,
                            )
                        )
                    ),
                ),
            )

            # Validate response structure before accessing
            if not response.candidates or not response.candidates[0].content.parts:
                raise ValueError("Gemini API returned no audio data in response")

            # Extract audio data from response
            audio_data = response.candidates[0].content.parts[0].inline_data.data

            # The data is base64 encoded
            if isinstance(audio_data, str):
                audio_bytes = base64.b64decode(audio_data)
            else:
                audio_bytes = audio_data

            logger.info(f"Gemini TTS synthesis successful: {len(audio_bytes)} bytes")
            return audio_bytes

        except Exception as e:
            logger.error(f"Gemini TTS synthesis failed: {e}")
            raise ValueError(f"Gemini TTS synthesis failed: {e}") from e

    def synthesize_multispeaker(
        self,
        text: str,
        speakers: Dict[str, str],
        prompt: Optional[str] = None,
        output_format: str = "wav",
        model: str = "flash",
    ) -> bytes:
        """Synthesize multi-speaker dialogue using Gemini TTS.

        Args:
            text: Dialogue text with speaker labels, e.g.:
                "Speaker1: Hello there!
                 Speaker2: Hi, how are you?"
            speakers: Dict mapping speaker aliases to voice names, e.g.:
                {"Speaker1": "Kore", "Speaker2": "Charon"}
            prompt: Optional styling instructions for the conversation
            output_format: Audio format (wav)
            model: Model: "flash" or "pro"

        Returns:
            Audio bytes with multi-speaker dialogue

        Raises:
            ValueError: If synthesis fails
        """
        from google.genai import types

        model_name = GEMINI_TTS_MODELS.get(model, GEMINI_TTS_MODELS["flash"])

        logger.info(
            f"Gemini TTS multi-speaker synthesis: "
            f"speakers={list(speakers.keys())}, model={model_name}"
        )

        # Build speaker voice configs
        speaker_voice_configs = []
        for alias, voice_id in speakers.items():
            speaker_voice_configs.append(
                types.SpeakerVoiceConfig(
                    speaker=alias,
                    voice_config=types.VoiceConfig(
                        prebuilt_voice_config=types.PrebuiltVoiceConfig(
                            voice_name=voice_id,
                        )
                    ),
                )
            )

        # Build the content - include prompt if provided
        if prompt:
            content = f"{prompt}\n\n{text}"
        else:
            content = text

        try:
            response = self.client.models.generate_content(
                model=model_name,
                contents=content,
                config=types.GenerateContentConfig(
                    response_modalities=["AUDIO"],
                    speech_config=types.SpeechConfig(
                        multi_speaker_voice_config=types.MultiSpeakerVoiceConfig(
                            speaker_voice_configs=speaker_voice_configs,
                        )
                    ),
                ),
            )

            # Validate response structure before accessing
            if not response.candidates or not response.candidates[0].content.parts:
                raise ValueError("Gemini API returned no audio data in response")

            # Extract audio data from response
            audio_data = response.candidates[0].content.parts[0].inline_data.data

            if isinstance(audio_data, str):
                audio_bytes = base64.b64decode(audio_data)
            else:
                audio_bytes = audio_data

            logger.info(
                f"Gemini TTS multi-speaker synthesis successful: {len(audio_bytes)} bytes"
            )
            return audio_bytes

        except Exception as e:
            logger.error(f"Gemini TTS multi-speaker synthesis failed: {e}")
            raise ValueError(f"Gemini TTS multi-speaker synthesis failed: {e}") from e


def is_gemini_api_available() -> bool:
    """Check if Gemini API is available (key configured)."""
    import os

    if os.getenv("GEMINI_API_KEY"):
        return True

    try:
        from appconfig.models import GlobalConfig

        config = GlobalConfig.objects.first()
        if config and hasattr(config, "gemini_api_key") and config.gemini_api_key:
            return True
    except Exception:
        pass

    return False
