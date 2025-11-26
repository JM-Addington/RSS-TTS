"""Tests for TTSService facade."""

from unittest.mock import MagicMock, patch

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

        # Generate speech with Chirp3-HD voice (not remapped)
        audio_bytes = service.generate_speech(
            text="Hello world",
            voice="en-US-Chirp3-HD-Charon",
            speed=1.2,
            instructions="Speak slowly",
            response_format="mp3",
        )

        # Verify result
        self.assertEqual(audio_bytes, b"google_audio_data")

        # Verify provider call
        mock_provider.synthesize_speech.assert_called_once_with(
            text="Hello world",
            voice_name="en-US-Chirp3-HD-Charon",
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

    # --- Gemini Provider Tests ---

    @patch("text_to_audio.services.tts_service.GeminiTTSProvider")
    def test_gemini_provider_lazy_loading(self, mock_gemini_class):
        """Test Gemini provider is lazy-loaded only when needed."""
        mock_provider = MagicMock()
        mock_gemini_class.return_value = mock_provider

        service = TTSService(provider="google")

        # Provider should not be loaded yet
        self.assertIsNone(service._gemini_provider)

        # Access provider property to trigger lazy loading
        provider = service.gemini_provider

        # Provider should now be loaded
        self.assertEqual(provider, mock_provider)
        mock_gemini_class.assert_called_once()

    # --- Voice Validation Tests ---

    def test_is_gemini_voice_returns_true_for_short_names(self):
        """Test _is_gemini_voice correctly identifies Gemini short voice names."""
        service = TTSService(provider="google")

        # Test various Gemini voice names
        self.assertTrue(service._is_gemini_voice("Kore"))
        self.assertTrue(service._is_gemini_voice("Charon"))
        self.assertTrue(service._is_gemini_voice("Aoede"))
        self.assertTrue(service._is_gemini_voice("Fenrir"))
        self.assertTrue(service._is_gemini_voice("Zephyr"))

    def test_is_gemini_voice_returns_false_for_long_names(self):
        """Test _is_gemini_voice returns False for full Cloud TTS names."""
        service = TTSService(provider="google")

        # Chirp3-HD voices
        self.assertFalse(service._is_gemini_voice("en-US-Chirp3-HD-Charon"))
        self.assertFalse(service._is_gemini_voice("en-US-Chirp3-HD-Kore"))

        # Neural2 voices
        self.assertFalse(service._is_gemini_voice("en-US-Neural2-A"))
        self.assertFalse(service._is_gemini_voice("en-US-Neural2-D"))

        # Journey voices
        self.assertFalse(service._is_gemini_voice("en-US-Journey-D"))

    def test_is_gemini_voice_returns_false_for_openai_voices(self):
        """Test _is_gemini_voice returns False for OpenAI voices."""
        service = TTSService(provider="google")

        self.assertFalse(service._is_gemini_voice("alloy"))
        self.assertFalse(service._is_gemini_voice("nova"))
        self.assertFalse(service._is_gemini_voice("echo"))

    def test_validate_voice_openai_provider_with_openai_voice(self):
        """Test voice validation passes OpenAI voice for OpenAI provider."""
        service = TTSService(provider="openai")

        result = service._validate_voice_for_provider("alloy")
        self.assertEqual(result, "alloy")

        result = service._validate_voice_for_provider("nova")
        self.assertEqual(result, "nova")

    def test_validate_voice_openai_provider_with_google_voice(self):
        """Test voice validation defaults to 'alloy' when Google voice used with OpenAI."""
        service = TTSService(provider="openai")

        result = service._validate_voice_for_provider("Kore")
        self.assertEqual(result, "alloy")

        result = service._validate_voice_for_provider("en-US-Chirp3-HD-Charon")
        self.assertEqual(result, "alloy")

    @patch("text_to_audio.services.tts_service.get_google_tts_voice_type")
    def test_validate_voice_google_provider_with_openai_voice(
        self, mock_get_voice_type
    ):
        """Test voice validation defaults to Gemini voice when OpenAI voice used with Google."""
        mock_get_voice_type.return_value = "gemini"

        service = TTSService(provider="google")

        result = service._validate_voice_for_provider("alloy")
        self.assertEqual(result, "Kore")  # Default Gemini voice

    def test_validate_voice_google_provider_with_gemini_voice(self):
        """Test voice validation passes Gemini short voice names for Google provider."""
        service = TTSService(provider="google")

        result = service._validate_voice_for_provider("Kore")
        self.assertEqual(result, "Kore")

        result = service._validate_voice_for_provider("Charon")
        self.assertEqual(result, "Charon")

    def test_validate_voice_google_provider_with_chirp3_voice(self):
        """Test voice validation passes Chirp3-HD voices for Google provider."""
        service = TTSService(provider="google")

        result = service._validate_voice_for_provider("en-US-Chirp3-HD-Charon")
        self.assertEqual(result, "en-US-Chirp3-HD-Charon")

    @patch("text_to_audio.services.tts_service.get_google_tts_voice_type")
    def test_validate_voice_google_provider_remaps_journey_voices(
        self, mock_get_voice_type
    ):
        """Test Journey voices are remapped to configured default for gemini/chirp3."""
        # AIDEV-NOTE: Journey voices are deprecated and should be remapped
        # when the configured voice type is gemini or chirp3
        mock_get_voice_type.return_value = "gemini"
        service = TTSService(provider="google")

        # Journey-D should be remapped to Kore (default gemini voice)
        result = service._validate_voice_for_provider("en-US-Journey-D")
        self.assertEqual(result, "Kore")

        result = service._validate_voice_for_provider("en-US-Journey-O")
        self.assertEqual(result, "Kore")

    @patch("text_to_audio.services.tts_service.get_google_tts_voice_type")
    def test_validate_voice_google_provider_remaps_journey_to_chirp3(
        self, mock_get_voice_type
    ):
        """Test Journey voices are remapped to chirp3 default when chirp3 is configured."""
        mock_get_voice_type.return_value = "chirp3"
        service = TTSService(provider="google")

        # Journey-D should be remapped to Chirp3-HD default
        result = service._validate_voice_for_provider("en-US-Journey-D")
        self.assertEqual(result, "en-US-Chirp3-HD-Charon")

    # --- Gemini Voice Routing Tests ---

    @patch("text_to_audio.services.tts_service.GeminiTTSProvider")
    def test_generate_speech_routes_gemini_voice_to_gemini_provider(
        self, mock_gemini_class
    ):
        """Test that Gemini short voice names are routed to GeminiTTSProvider."""
        mock_provider = MagicMock()
        mock_provider.synthesize_speech.return_value = b"gemini_audio_data"
        mock_gemini_class.return_value = mock_provider

        service = TTSService(provider="google")

        # Generate speech with Gemini voice
        audio_bytes = service.generate_speech(
            text="Hello world",
            voice="Kore",  # Gemini short name
            speed=1.0,
            instructions="Speak warmly",
            response_format="wav",
        )

        # Verify result
        self.assertEqual(audio_bytes, b"gemini_audio_data")

        # Verify Gemini provider was called (not Google Cloud TTS)
        mock_provider.synthesize_speech.assert_called_once_with(
            text="Hello world",
            voice_name="Kore",
            prompt="Speak warmly",
            output_format="wav",
            model="flash",
        )

    @patch("text_to_audio.services.tts_service.GoogleTTSProvider")
    def test_generate_speech_routes_chirp3_voice_to_google_provider(
        self, mock_google_class
    ):
        """Test that Chirp3-HD voice names are routed to GoogleTTSProvider."""
        mock_provider = MagicMock()
        mock_provider.synthesize_speech.return_value = b"google_cloud_audio_data"
        mock_google_class.return_value = mock_provider

        service = TTSService(provider="google")

        # Generate speech with Chirp3-HD voice
        audio_bytes = service.generate_speech(
            text="Hello world",
            voice="en-US-Chirp3-HD-Charon",  # Full Cloud TTS name
            speed=1.2,
            response_format="mp3",
        )

        # Verify result
        self.assertEqual(audio_bytes, b"google_cloud_audio_data")

        # Verify Google Cloud TTS provider was called
        mock_provider.synthesize_speech.assert_called_once()

    @patch("text_to_audio.services.tts_service.GeminiTTSProvider")
    @patch("text_to_audio.services.tts_service.GoogleTTSProvider")
    def test_generate_speech_gemini_fallback_to_google_on_error(
        self, mock_google_class, mock_gemini_class
    ):
        """Test that Gemini failures fall back to Google Cloud TTS."""
        # Gemini provider fails
        mock_gemini_provider = MagicMock()
        mock_gemini_provider.synthesize_speech.side_effect = Exception(
            "Gemini API error"
        )
        mock_gemini_class.return_value = mock_gemini_provider

        # Google provider succeeds
        mock_google_provider = MagicMock()
        mock_google_provider.synthesize_speech.return_value = b"fallback_audio"
        mock_google_class.return_value = mock_google_provider

        service = TTSService(provider="google")

        # Generate speech with Gemini voice - should fall back to Google
        audio_bytes = service.generate_speech(
            text="Hello world",
            voice="Kore",  # Gemini short name
        )

        # Verify fallback to Google provider
        self.assertEqual(audio_bytes, b"fallback_audio")
        mock_gemini_provider.synthesize_speech.assert_called_once()
        mock_google_provider.synthesize_speech.assert_called_once()
