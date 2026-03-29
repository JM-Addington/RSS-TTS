"""Integration tests for TTS providers.

These tests make actual API calls and require credentials to be configured.
They are marked with pytest.mark.integration and will be skipped if credentials
are not available.

Run with: pytest tests/text_to_audio/test_tts_integration.py -v -m integration
"""

import os
import unittest

from django.test import TestCase


def _is_placeholder_key(key):
    """Check if an API key is a placeholder (not real)."""
    return not key or key.startswith("your-")


def skip_if_no_gemini_key():
    """Skip test if Gemini API key is not configured."""
    return _is_placeholder_key(os.getenv("GEMINI_API_KEY", "")) and _is_placeholder_key(
        os.getenv("GOOGLE_TTS_API_KEY", "")
    )


def skip_if_no_google_credentials():
    """Skip test if Google Cloud TTS credentials are not configured."""
    return _is_placeholder_key(
        os.getenv("GOOGLE_TTS_API_KEY", "")
    ) and _is_placeholder_key(os.getenv("GOOGLE_TTS_CREDENTIALS_JSON", ""))


def skip_if_no_openai_key():
    """Skip test if OpenAI API key is not configured."""
    return _is_placeholder_key(os.getenv("OPENAI_API_KEY", ""))


@unittest.skipIf(skip_if_no_gemini_key(), "Gemini API key not configured")
class GeminiTTSIntegrationTest(TestCase):
    """Integration tests for Gemini TTS provider (AI Studio API)."""

    @classmethod
    def setUpClass(cls):
        """Set up test fixtures."""
        super().setUpClass()
        from text_to_audio.services.gemini_tts_provider import \
            GeminiTTSProvider

        cls.provider = GeminiTTSProvider()

    def test_synthesize_speech_basic(self):
        """Test basic speech synthesis returns audio bytes."""
        audio_bytes = self.provider.synthesize_speech(
            text="Hello, this is a test.",
            voice_name="Kore",
            model="flash",
        )

        self.assertIsInstance(audio_bytes, bytes)
        self.assertGreater(len(audio_bytes), 1000)  # Should be reasonable size

    def test_synthesize_speech_with_prompt(self):
        """Test speech synthesis with styling prompt."""
        audio_bytes = self.provider.synthesize_speech(
            text="Welcome to the kingdom.",
            voice_name="Charon",
            prompt="Speak in a warm, welcoming tone",
            model="flash",
        )

        self.assertIsInstance(audio_bytes, bytes)
        self.assertGreater(len(audio_bytes), 1000)

    def test_synthesize_speech_different_voices(self):
        """Test synthesis with different voice names."""
        voices = ["Kore", "Charon", "Aoede", "Fenrir"]

        for voice in voices:
            with self.subTest(voice=voice):
                audio_bytes = self.provider.synthesize_speech(
                    text="Testing voice.",
                    voice_name=voice,
                    model="flash",
                )
                self.assertIsInstance(audio_bytes, bytes)
                self.assertGreater(len(audio_bytes), 500)

    def test_synthesize_multispeaker(self):
        """Test multi-speaker dialogue synthesis."""
        dialogue = "Alice: Hello!\nBob: Hi there, how are you?"
        speakers = {"Alice": "Kore", "Bob": "Charon"}

        audio_bytes = self.provider.synthesize_multispeaker(
            text=dialogue,
            speakers=speakers,
            model="flash",
        )

        self.assertIsInstance(audio_bytes, bytes)
        self.assertGreater(len(audio_bytes), 1000)

    def test_synthesize_multispeaker_with_prompt(self):
        """Test multi-speaker with styling prompt."""
        dialogue = "Narrator: Once upon a time...\nPrincess: I shall save the kingdom!"
        speakers = {"Narrator": "Charon", "Princess": "Kore"}

        audio_bytes = self.provider.synthesize_multispeaker(
            text=dialogue,
            speakers=speakers,
            prompt="A dramatic fairy tale narration",
            model="flash",
        )

        self.assertIsInstance(audio_bytes, bytes)
        self.assertGreater(len(audio_bytes), 1000)


@unittest.skipIf(
    skip_if_no_google_credentials(), "Google Cloud TTS credentials not configured"
)
class GoogleCloudTTSIntegrationTest(TestCase):
    """Integration tests for Google Cloud TTS provider (Chirp3-HD, Neural2)."""

    @classmethod
    def setUpClass(cls):
        """Set up test fixtures."""
        super().setUpClass()
        from text_to_audio.services.google_tts_provider import \
            GoogleTTSProvider

        cls.provider = GoogleTTSProvider()

    def test_synthesize_speech_chirp3(self):
        """Test Chirp3-HD voice synthesis."""
        audio_bytes = self.provider.synthesize_speech(
            text="Hello, this is a test.",
            voice_name="en-US-Chirp3-HD-Charon",
            speed=1.0,
            output_format="wav",
        )

        self.assertIsInstance(audio_bytes, bytes)
        self.assertGreater(len(audio_bytes), 1000)

    def test_synthesize_speech_neural2(self):
        """Test Neural2 voice synthesis."""
        audio_bytes = self.provider.synthesize_speech(
            text="Hello, this is a test.",
            voice_name="en-US-Neural2-A",
            speed=1.0,
            output_format="wav",
        )

        self.assertIsInstance(audio_bytes, bytes)
        self.assertGreater(len(audio_bytes), 1000)

    def test_synthesize_speech_with_speed(self):
        """Test synthesis with different speaking rates."""
        speeds = [0.8, 1.0, 1.2]

        for speed in speeds:
            with self.subTest(speed=speed):
                audio_bytes = self.provider.synthesize_speech(
                    text="Testing speed variation.",
                    voice_name="en-US-Neural2-D",
                    speed=speed,
                )
                self.assertIsInstance(audio_bytes, bytes)
                self.assertGreater(len(audio_bytes), 500)

    def test_synthesize_speech_mp3_format(self):
        """Test synthesis with MP3 output format."""
        audio_bytes = self.provider.synthesize_speech(
            text="Testing MP3 format.",
            voice_name="en-US-Chirp3-HD-Kore",
            output_format="mp3",
        )

        self.assertIsInstance(audio_bytes, bytes)
        self.assertGreater(len(audio_bytes), 500)


@unittest.skipIf(skip_if_no_openai_key(), "OpenAI API key not configured")
class OpenAITTSIntegrationTest(TestCase):
    """Integration tests for OpenAI TTS provider."""

    @classmethod
    def setUpClass(cls):
        """Set up test fixtures."""
        super().setUpClass()
        from text_to_audio.services.tts_service import TTSService

        cls.service = TTSService(provider="openai")

    def test_generate_speech_basic(self):
        """Test basic OpenAI speech synthesis."""
        audio_bytes = self.service.generate_speech(
            text="Hello, this is a test.",
            voice="alloy",
            speed=1.0,
            response_format="wav",
        )

        self.assertIsInstance(audio_bytes, bytes)
        self.assertGreater(len(audio_bytes), 1000)

    def test_generate_speech_different_voices(self):
        """Test synthesis with different OpenAI voices."""
        voices = ["alloy", "nova", "echo", "shimmer"]

        for voice in voices:
            with self.subTest(voice=voice):
                audio_bytes = self.service.generate_speech(
                    text="Testing voice.",
                    voice=voice,
                )
                self.assertIsInstance(audio_bytes, bytes)
                self.assertGreater(len(audio_bytes), 500)

    def test_generate_speech_with_speed(self):
        """Test synthesis with different speeds."""
        audio_bytes = self.service.generate_speech(
            text="Testing speed.",
            voice="alloy",
            speed=1.5,
        )

        self.assertIsInstance(audio_bytes, bytes)
        self.assertGreater(len(audio_bytes), 500)


@unittest.skipIf(
    skip_if_no_gemini_key() and skip_if_no_google_credentials(),
    "No Google TTS credentials configured",
)
class TTSServiceGoogleRoutingIntegrationTest(TestCase):
    """Integration tests for TTSService Google provider routing."""

    @classmethod
    def setUpClass(cls):
        """Set up test fixtures."""
        super().setUpClass()
        from text_to_audio.services.tts_service import TTSService

        cls.service = TTSService(provider="google")

    @unittest.skipIf(skip_if_no_gemini_key(), "Gemini API key not configured")
    def test_routes_gemini_voice_to_gemini_api(self):
        """Test that Gemini short names are routed to Gemini AI Studio API."""
        audio_bytes = self.service.generate_speech(
            text="Hello from Gemini.",
            voice="Kore",  # Short Gemini name
            instructions="Speak warmly",
        )

        self.assertIsInstance(audio_bytes, bytes)
        self.assertGreater(len(audio_bytes), 1000)

    @unittest.skipIf(
        skip_if_no_google_credentials(), "Google Cloud TTS credentials not configured"
    )
    def test_routes_chirp3_voice_to_cloud_api(self):
        """Test that Chirp3-HD names are routed to Google Cloud TTS API."""
        audio_bytes = self.service.generate_speech(
            text="Hello from Cloud TTS.",
            voice="en-US-Chirp3-HD-Charon",  # Full Cloud TTS name
        )

        self.assertIsInstance(audio_bytes, bytes)
        self.assertGreater(len(audio_bytes), 1000)

    @unittest.skipIf(skip_if_no_gemini_key(), "Gemini API key not configured")
    def test_prompt_passed_to_gemini(self):
        """Test that styling prompts work with Gemini voices."""
        # With prompt
        audio_with_prompt = self.service.generate_speech(
            text="Welcome to the realm.",
            voice="Charon",
            instructions="Speak in a deep, mysterious voice",
        )

        # Without prompt (for comparison)
        audio_without_prompt = self.service.generate_speech(
            text="Welcome to the realm.",
            voice="Charon",
        )

        # Both should succeed
        self.assertIsInstance(audio_with_prompt, bytes)
        self.assertIsInstance(audio_without_prompt, bytes)
        self.assertGreater(len(audio_with_prompt), 1000)
        self.assertGreater(len(audio_without_prompt), 1000)
