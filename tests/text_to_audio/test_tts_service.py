"""Tests for TTSService facade."""

from unittest.mock import MagicMock, Mock, patch

from django.test import TestCase

from text_to_audio.services.tts_service import TTSService


class TTSServiceTest(TestCase):
    """Test TTSService provider abstraction."""

    def setUp(self):
        """Set up test fixtures."""
        self.mock_openai_api_key = "test-openai-key"
        self.mock_google_credentials = {
            "type": "service_account",
            "project_id": "test-project",
            "private_key": "test-key",
            "client_email": "test@test.iam.gserviceaccount.com",
        }

    @patch("text_to_audio.services.tts_service.get_default_tts_provider")
    def test_init_defaults_to_global_config(self, mock_get_provider):
        """Test TTSService uses global config when no provider specified."""
        mock_get_provider.return_value = "openai"

        service = TTSService()

        self.assertEqual(service.provider, "openai")
        mock_get_provider.assert_called_once()

    def test_init_with_explicit_provider(self):
        """Test TTSService respects explicit provider parameter."""
        service = TTSService(provider="google")

        self.assertEqual(service.provider, "google")

    @patch("text_to_audio.services.tts_service.get_openai_api_key")
    @patch("text_to_audio.services.tts_service.openai.OpenAI")
    def test_openai_client_lazy_loading(self, mock_openai_class, mock_get_key):
        """Test OpenAI client is lazy-loaded only when needed."""
        mock_get_key.return_value = self.mock_openai_api_key
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client

        service = TTSService(provider="openai")

        # Client should not be loaded yet
        self.assertIsNone(service._openai_client)

        # Access client property to trigger lazy loading
        client = service.openai_client

        # Client should now be loaded
        self.assertEqual(client, mock_client)
        mock_openai_class.assert_called_once_with(api_key=self.mock_openai_api_key)

    @patch("text_to_audio.services.tts_service.get_openai_api_key")
    def test_openai_client_raises_without_api_key(self, mock_get_key):
        """Test OpenAI client raises ValueError if API key not configured."""
        mock_get_key.return_value = None

        service = TTSService(provider="openai")

        with self.assertRaises(ValueError) as cm:
            _ = service.openai_client

        self.assertIn("OpenAI API key not configured", str(cm.exception))

    @patch("text_to_audio.services.tts_service.GoogleTTSProvider")
    def test_google_provider_lazy_loading(self, mock_google_class):
        """Test Google provider is lazy-loaded only when needed."""
        mock_provider = MagicMock()
        mock_google_class.return_value = mock_provider

        service = TTSService(provider="google")

        # Provider should not be loaded yet
        self.assertIsNone(service._google_provider)

        # Access provider property to trigger lazy loading
        provider = service.google_provider

        # Provider should now be loaded
        self.assertEqual(provider, mock_provider)
        mock_google_class.assert_called_once()

    def test_get_char_limit_openai(self):
        """Test character limit for OpenAI provider."""
        service = TTSService(provider="openai")

        limit = service.get_char_limit()

        self.assertEqual(limit, 4096)

    def test_get_char_limit_google(self):
        """Test character limit for Google provider."""
        service = TTSService(provider="google")

        limit = service.get_char_limit()

        self.assertEqual(limit, 4000)

    def test_get_char_limit_unknown_provider(self):
        """Test character limit defaults to 4000 for unknown providers."""
        service = TTSService(provider="unknown")

        limit = service.get_char_limit()

        self.assertEqual(limit, 4000)

    @patch("text_to_audio.services.tts_service.get_openai_api_key")
    @patch("text_to_audio.services.tts_service.openai.OpenAI")
    @patch("text_to_audio.services.tts_service.get_openai_tts_model")
    def test_generate_speech_openai_basic(
        self, mock_get_model, mock_openai_class, mock_get_key
    ):
        """Test OpenAI speech generation with basic parameters."""
        mock_get_key.return_value = "test-key"
        mock_get_model.return_value = "tts-1-hd"

        # Mock OpenAI client and response
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client

        mock_response = MagicMock()
        mock_response.iter_bytes.return_value = [b"chunk1", b"chunk2"]
        mock_client.audio.speech.create.return_value = mock_response

        service = TTSService(provider="openai")

        # Generate speech
        audio_bytes = service.generate_speech(
            text="Hello world", voice="alloy", speed=1.0, response_format="wav"
        )

        # Verify result
        self.assertEqual(audio_bytes, b"chunk1chunk2")

        # Verify API call
        mock_client.audio.speech.create.assert_called_once_with(
            model="tts-1-hd",
            voice="alloy",
            input="Hello world",
            response_format="wav",
        )

    @patch("text_to_audio.services.tts_service.get_openai_api_key")
    @patch("text_to_audio.services.tts_service.openai.OpenAI")
    @patch("text_to_audio.services.tts_service.get_openai_tts_model")
    def test_generate_speech_openai_with_speed(
        self, mock_get_model, mock_openai_class, mock_get_key
    ):
        """Test OpenAI speech generation includes speed when not default."""
        mock_get_key.return_value = "test-key"
        mock_get_model.return_value = "tts-1-hd"

        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client

        mock_response = MagicMock()
        mock_response.iter_bytes.return_value = [b"audio"]
        mock_client.audio.speech.create.return_value = mock_response

        service = TTSService(provider="openai")

        # Generate speech with non-default speed
        service.generate_speech(text="Test", voice="nova", speed=1.5)

        # Verify speed is included in API call
        call_args = mock_client.audio.speech.create.call_args[1]
        self.assertEqual(call_args["speed"], 1.5)

    @patch("text_to_audio.services.tts_service.get_openai_api_key")
    @patch("text_to_audio.services.tts_service.openai.OpenAI")
    @patch("text_to_audio.services.tts_service.get_openai_tts_model")
    def test_generate_speech_openai_with_instructions(
        self, mock_get_model, mock_openai_class, mock_get_key
    ):
        """Test OpenAI speech generation includes instructions for supported models."""
        mock_get_key.return_value = "test-key"
        mock_get_model.return_value = "tts-1-hd"

        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client

        mock_response = MagicMock()
        mock_response.iter_bytes.return_value = [b"audio"]
        mock_client.audio.speech.create.return_value = mock_response

        service = TTSService(provider="openai")

        # Generate speech with instructions
        service.generate_speech(
            text="Test",
            voice="alloy",
            model="tts-1-hd",
            instructions="Speak in a warm, friendly tone",
        )

        # Verify instructions are included
        call_args = mock_client.audio.speech.create.call_args[1]
        self.assertEqual(call_args["instructions"], "Speak in a warm, friendly tone")

    @patch("text_to_audio.services.tts_service.GoogleTTSProvider")
    def test_generate_speech_google(self, mock_google_class):
        """Test Google speech generation delegates to provider."""
        mock_provider = MagicMock()
        mock_provider.synthesize_speech.return_value = b"google_audio_data"
        mock_google_class.return_value = mock_provider

        service = TTSService(provider="google")

        # Generate speech
        audio_bytes = service.generate_speech(
            text="Hello world",
            voice="en-US-Journey-D",
            speed=1.2,
            instructions="Speak slowly",
            response_format="mp3",
        )

        # Verify result
        self.assertEqual(audio_bytes, b"google_audio_data")

        # Verify provider call
        mock_provider.synthesize_speech.assert_called_once_with(
            text="Hello world",
            voice_name="en-US-Journey-D",
            speed=1.2,
            prompt="Speak slowly",
            output_format="mp3",
        )

    def test_generate_speech_unknown_provider(self):
        """Test generate_speech raises ValueError for unknown provider."""
        service = TTSService(provider="elevenlabs")

        with self.assertRaises(ValueError) as cm:
            service.generate_speech(text="Test", voice="test")

        self.assertIn("Unknown TTS provider: elevenlabs", str(cm.exception))
