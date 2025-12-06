"""Tests for GoogleTTSProvider."""

import json
from unittest.mock import MagicMock, patch

from django.test import TestCase


class GoogleTTSProviderTest(TestCase):
    """Test GoogleTTSProvider implementation."""

    def setUp(self):
        """Set up test fixtures."""
        self.mock_credentials = {
            "type": "service_account",
            "project_id": "test-project",
            "private_key": "-----BEGIN PRIVATE KEY-----\ntest\n-----END PRIVATE KEY-----\n",
            "private_key_id": "test-key-id",
            "client_email": "test@test.iam.gserviceaccount.com",
            "client_id": "123456789",
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }

    def _create_provider_with_mocks(self):
        """Helper to create a GoogleTTSProvider with mocked dependencies."""
        with patch("appconfig.utils.get_google_tts_api_key") as mock_api_key, patch(
            "appconfig.utils.get_google_tts_credentials"
        ) as mock_creds:
            mock_api_key.return_value = "test-api-key"
            mock_creds.return_value = None

            # Mock the Google Cloud client
            with patch(
                "google.api_core.client_options.ClientOptions"
            ) as mock_client_opts, patch(
                "google.cloud.texttospeech_v1.TextToSpeechClient"
            ) as mock_tts_client:
                mock_client_opts.return_value = MagicMock()
                mock_client = MagicMock()
                mock_tts_client.return_value = mock_client

                from text_to_audio.services.google_tts_provider import (
                    GoogleTTSProvider,
                )

                provider = GoogleTTSProvider()
                return provider, mock_client

    def test_init_raises_without_credentials(self):
        """Test GoogleTTSProvider raises ValueError if credentials not configured."""
        with patch("appconfig.utils.get_google_tts_api_key") as mock_api_key, patch(
            "appconfig.utils.get_google_tts_credentials"
        ) as mock_creds:
            mock_api_key.return_value = None
            mock_creds.return_value = None

            from text_to_audio.services.google_tts_provider import GoogleTTSProvider

            with self.assertRaises(ValueError) as cm:
                GoogleTTSProvider()

            self.assertIn("Google TTS credentials not configured", str(cm.exception))

    def test_init_with_dict_credentials(self):
        """Test GoogleTTSProvider initializes with dict credentials."""
        with patch("appconfig.utils.get_google_tts_api_key") as mock_api_key, patch(
            "appconfig.utils.get_google_tts_credentials"
        ) as mock_creds, patch(
            "google.oauth2.service_account.Credentials.from_service_account_info"
        ) as mock_from_sa, patch(
            "google.cloud.texttospeech_v1.TextToSpeechClient"
        ) as mock_tts_client:
            mock_api_key.return_value = None  # No API key
            mock_creds.return_value = self.mock_credentials  # Service account creds

            mock_credentials_obj = MagicMock()
            mock_from_sa.return_value = mock_credentials_obj

            mock_client = MagicMock()
            mock_tts_client.return_value = mock_client

            from text_to_audio.services.google_tts_provider import GoogleTTSProvider

            provider = GoogleTTSProvider()

            # Verify credentials were parsed
            mock_from_sa.assert_called_once_with(self.mock_credentials)

            # Verify client was created
            mock_tts_client.assert_called_once_with(credentials=mock_credentials_obj)

            self.assertEqual(provider.client, mock_client)

    def test_init_with_string_credentials(self):
        """Test GoogleTTSProvider parses string credentials."""
        credentials_json = json.dumps(self.mock_credentials)

        with patch("appconfig.utils.get_google_tts_api_key") as mock_api_key, patch(
            "appconfig.utils.get_google_tts_credentials"
        ) as mock_creds, patch(
            "google.oauth2.service_account.Credentials.from_service_account_info"
        ) as mock_from_sa, patch(
            "google.cloud.texttospeech_v1.TextToSpeechClient"
        ) as mock_tts_client:
            mock_api_key.return_value = None
            mock_creds.return_value = credentials_json

            mock_credentials_obj = MagicMock()
            mock_from_sa.return_value = mock_credentials_obj

            mock_client = MagicMock()
            mock_tts_client.return_value = mock_client

            from text_to_audio.services.google_tts_provider import GoogleTTSProvider

            provider = GoogleTTSProvider()

            # Verify credentials were parsed from JSON string
            mock_from_sa.assert_called_once()

            self.assertIsNotNone(provider.client)

    def test_init_raises_on_invalid_json(self):
        """Test GoogleTTSProvider raises ValueError on invalid JSON credentials."""
        with patch("appconfig.utils.get_google_tts_api_key") as mock_api_key, patch(
            "appconfig.utils.get_google_tts_credentials"
        ) as mock_creds:
            mock_api_key.return_value = None
            mock_creds.return_value = "invalid json {{"

            from text_to_audio.services.google_tts_provider import GoogleTTSProvider

            with self.assertRaises(ValueError) as cm:
                GoogleTTSProvider()

            self.assertIn("Invalid Google TTS credentials JSON", str(cm.exception))

    def test_get_voice_type_gemini(self):
        """Test voice type detection for Gemini voices."""
        provider, _ = self._create_provider_with_mocks()

        # Test Journey voice (Gemini)
        voice_type = provider._get_voice_type("en-US-Journey-D")
        self.assertEqual(voice_type, "gemini")

        # Test short Gemini voice name
        voice_type = provider._get_voice_type("Charon")
        self.assertEqual(voice_type, "gemini")

    def test_get_voice_type_chirp3(self):
        """Test voice type detection for Chirp3 voices."""
        provider, _ = self._create_provider_with_mocks()

        voice_type = provider._get_voice_type("en-US-Chirp3-HD-Charon")
        self.assertEqual(voice_type, "chirp3")

    def test_get_voice_type_neural2(self):
        """Test voice type detection for Neural2 voices."""
        provider, _ = self._create_provider_with_mocks()

        voice_type = provider._get_voice_type("en-US-Neural2-A")
        self.assertEqual(voice_type, "neural2")

    def test_get_voice_type_unknown_defaults(self):
        """Test voice type defaults to config value for unknown voices."""
        with patch(
            "appconfig.utils.get_google_tts_voice_type"
        ) as mock_get_default_type:
            mock_get_default_type.return_value = "gemini"

            provider, _ = self._create_provider_with_mocks()

            voice_type = provider._get_voice_type("en-US-Unknown-Voice")
            self.assertEqual(voice_type, "gemini")
            mock_get_default_type.assert_called_once()

    def test_build_voice_params_basic(self):
        """Test building voice parameters for non-gemini voice."""
        provider, _ = self._create_provider_with_mocks()

        with patch(
            "google.cloud.texttospeech_v1.VoiceSelectionParams"
        ) as mock_voice_params_cls:
            mock_voice_params = MagicMock()
            mock_voice_params_cls.return_value = mock_voice_params

            # Test non-gemini voice (chirp3) - doesn't use model_name
            result = provider._build_voice_params(
                "en-US-Chirp3-HD-Charon", "chirp3", "pro"
            )

            # Verify VoiceSelectionParams called with correct language code and name
            mock_voice_params_cls.assert_called_with(
                language_code="en-US", name="en-US-Chirp3-HD-Charon"
            )

            self.assertEqual(result, mock_voice_params)

    def test_build_voice_params_extracts_language_code(self):
        """Test language code extraction from voice name."""
        provider, _ = self._create_provider_with_mocks()

        with patch(
            "google.cloud.texttospeech_v1.VoiceSelectionParams"
        ) as mock_voice_params_cls:
            provider._build_voice_params("fr-FR-Neural2-B", "neural2", None)

            # Verify language code extracted correctly
            call_args = mock_voice_params_cls.call_args[1]
            self.assertEqual(call_args["language_code"], "fr-FR")

    def test_build_voice_params_defaults_language_code(self):
        """Test language code defaults to en-US for invalid formats."""
        provider, _ = self._create_provider_with_mocks()

        with patch(
            "google.cloud.texttospeech_v1.VoiceSelectionParams"
        ) as mock_voice_params_cls:
            # For non-gemini voice type, test with invalid format
            provider._build_voice_params("InvalidVoiceName", "neural2", None)

            # Verify language code defaults to en-US
            call_args = mock_voice_params_cls.call_args[1]
            self.assertEqual(call_args["language_code"], "en-US")

    def test_get_audio_encoding_mp3(self):
        """Test audio encoding mapping for MP3."""
        from google.cloud import texttospeech_v1

        provider, _ = self._create_provider_with_mocks()

        encoding = provider._get_audio_encoding("mp3")

        self.assertEqual(encoding, texttospeech_v1.AudioEncoding.MP3)

    def test_get_audio_encoding_wav(self):
        """Test audio encoding mapping for WAV."""
        from google.cloud import texttospeech_v1

        provider, _ = self._create_provider_with_mocks()

        encoding = provider._get_audio_encoding("wav")

        self.assertEqual(encoding, texttospeech_v1.AudioEncoding.LINEAR16)

    def test_get_audio_encoding_defaults(self):
        """Test audio encoding defaults to LINEAR16 for unknown formats."""
        from google.cloud import texttospeech_v1

        provider, _ = self._create_provider_with_mocks()

        encoding = provider._get_audio_encoding("unknown")

        self.assertEqual(encoding, texttospeech_v1.AudioEncoding.LINEAR16)

    def test_synthesize_speech_success(self):
        """Test successful speech synthesis."""
        provider, mock_client = self._create_provider_with_mocks()

        mock_response = MagicMock()
        mock_response.audio_content = b"synthesized_audio_data"
        mock_client.synthesize_speech.return_value = mock_response

        # Synthesize speech (use Neural2 voice for simpler test)
        audio_bytes = provider.synthesize_speech(
            text="Hello world",
            voice_name="en-US-Neural2-A",
            speed=1.0,
            output_format="wav",
        )

        # Verify result
        self.assertEqual(audio_bytes, b"synthesized_audio_data")

        # Verify API was called
        mock_client.synthesize_speech.assert_called_once()

    def test_synthesize_speech_with_speed(self):
        """Test speech synthesis includes speaking rate for non-gemini voices."""
        provider, mock_client = self._create_provider_with_mocks()

        mock_response = MagicMock()
        mock_response.audio_content = b"audio"
        mock_client.synthesize_speech.return_value = mock_response

        with patch("google.cloud.texttospeech_v1.AudioConfig") as mock_audio_config:
            mock_audio_config.return_value = MagicMock()

            # Synthesize with custom speed (use Neural2 voice which supports speaking_rate)
            provider.synthesize_speech(
                text="Test", voice_name="en-US-Neural2-A", speed=1.5
            )

            # Verify AudioConfig was called with speaking_rate
            mock_audio_config.assert_called()
            call_kwargs = mock_audio_config.call_args[1]
            self.assertEqual(call_kwargs.get("speaking_rate"), 1.5)

    def test_synthesize_speech_api_error(self):
        """Test speech synthesis handles API errors."""
        provider, mock_client = self._create_provider_with_mocks()

        # Simulate API error
        mock_client.synthesize_speech.side_effect = Exception("API Error")

        with self.assertRaises(ValueError) as cm:
            provider.synthesize_speech(text="Test", voice_name="en-US-Neural2-A")

        self.assertIn("Google TTS synthesis failed", str(cm.exception))
