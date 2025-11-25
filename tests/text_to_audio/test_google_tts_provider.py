"""Tests for GoogleTTSProvider."""

from unittest.mock import MagicMock, Mock, patch

from django.test import TestCase

from text_to_audio.services.google_tts_provider import GoogleTTSProvider


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

    @patch("text_to_audio.services.google_tts_provider.get_google_tts_credentials")
    def test_init_raises_without_credentials(self, mock_get_creds):
        """Test GoogleTTSProvider raises ValueError if credentials not configured."""
        mock_get_creds.return_value = None

        with self.assertRaises(ValueError) as cm:
            GoogleTTSProvider()

        self.assertIn("Google TTS credentials not configured", str(cm.exception))

    @patch("text_to_audio.services.google_tts_provider.get_google_tts_credentials")
    @patch("text_to_audio.services.google_tts_provider.service_account")
    @patch("text_to_audio.services.google_tts_provider.texttospeech_v1")
    def test_init_with_dict_credentials(
        self, mock_tts_v1, mock_service_account, mock_get_creds
    ):
        """Test GoogleTTSProvider initializes with dict credentials."""
        mock_get_creds.return_value = self.mock_credentials

        mock_credentials_obj = MagicMock()
        mock_service_account.Credentials.from_service_account_info.return_value = (
            mock_credentials_obj
        )

        mock_client = MagicMock()
        mock_tts_v1.TextToSpeechClient.return_value = mock_client

        provider = GoogleTTSProvider()

        # Verify credentials were parsed
        mock_service_account.Credentials.from_service_account_info.assert_called_once_with(
            self.mock_credentials
        )

        # Verify client was created
        mock_tts_v1.TextToSpeechClient.assert_called_once_with(
            credentials=mock_credentials_obj
        )

        self.assertEqual(provider.client, mock_client)

    @patch("text_to_audio.services.google_tts_provider.get_google_tts_credentials")
    @patch("text_to_audio.services.google_tts_provider.service_account")
    @patch("text_to_audio.services.google_tts_provider.texttospeech_v1")
    @patch("text_to_audio.services.google_tts_provider.json.loads")
    def test_init_with_string_credentials(
        self, mock_json_loads, mock_tts_v1, mock_service_account, mock_get_creds
    ):
        """Test GoogleTTSProvider parses string credentials."""
        credentials_json = '{"type": "service_account", "project_id": "test"}'
        mock_get_creds.return_value = credentials_json
        mock_json_loads.return_value = self.mock_credentials

        mock_credentials_obj = MagicMock()
        mock_service_account.Credentials.from_service_account_info.return_value = (
            mock_credentials_obj
        )

        mock_client = MagicMock()
        mock_tts_v1.TextToSpeechClient.return_value = mock_client

        provider = GoogleTTSProvider()

        # Verify JSON was parsed
        mock_json_loads.assert_called_once_with(credentials_json)

        self.assertIsNotNone(provider.client)

    @patch("text_to_audio.services.google_tts_provider.get_google_tts_credentials")
    def test_init_raises_on_invalid_json(self, mock_get_creds):
        """Test GoogleTTSProvider raises ValueError on invalid JSON credentials."""
        mock_get_creds.return_value = "invalid json {{"

        with self.assertRaises(ValueError) as cm:
            GoogleTTSProvider()

        self.assertIn("Invalid Google TTS credentials JSON", str(cm.exception))

    def test_get_voice_type_gemini(self):
        """Test voice type detection for Gemini voices."""
        with patch(
            "text_to_audio.services.google_tts_provider.get_google_tts_credentials"
        ) as mock_get_creds:
            mock_get_creds.return_value = self.mock_credentials
            with patch(
                "text_to_audio.services.google_tts_provider.service_account"
            ), patch("text_to_audio.services.google_tts_provider.texttospeech_v1"):
                provider = GoogleTTSProvider()

                # Test Journey voice (Gemini)
                voice_type = provider._get_voice_type("en-US-Journey-D")
                self.assertEqual(voice_type, "gemini")

                # Test Gemini in name
                voice_type = provider._get_voice_type("en-US-Gemini-A")
                self.assertEqual(voice_type, "gemini")

    def test_get_voice_type_chirp3(self):
        """Test voice type detection for Chirp3 voices."""
        with patch(
            "text_to_audio.services.google_tts_provider.get_google_tts_credentials"
        ) as mock_get_creds:
            mock_get_creds.return_value = self.mock_credentials
            with patch(
                "text_to_audio.services.google_tts_provider.service_account"
            ), patch("text_to_audio.services.google_tts_provider.texttospeech_v1"):
                provider = GoogleTTSProvider()

                voice_type = provider._get_voice_type("en-US-Chirp3-HD-Charon")
                self.assertEqual(voice_type, "chirp3")

    def test_get_voice_type_neural2(self):
        """Test voice type detection for Neural2 voices."""
        with patch(
            "text_to_audio.services.google_tts_provider.get_google_tts_credentials"
        ) as mock_get_creds:
            mock_get_creds.return_value = self.mock_credentials
            with patch(
                "text_to_audio.services.google_tts_provider.service_account"
            ), patch("text_to_audio.services.google_tts_provider.texttospeech_v1"):
                provider = GoogleTTSProvider()

                voice_type = provider._get_voice_type("en-US-Neural2-A")
                self.assertEqual(voice_type, "neural2")

    @patch("text_to_audio.services.google_tts_provider.get_google_tts_voice_type")
    def test_get_voice_type_unknown_defaults(self, mock_get_default_type):
        """Test voice type defaults to config value for unknown voices."""
        mock_get_default_type.return_value = "gemini"

        with patch(
            "text_to_audio.services.google_tts_provider.get_google_tts_credentials"
        ) as mock_get_creds:
            mock_get_creds.return_value = self.mock_credentials
            with patch(
                "text_to_audio.services.google_tts_provider.service_account"
            ), patch("text_to_audio.services.google_tts_provider.texttospeech_v1"):
                provider = GoogleTTSProvider()

                voice_type = provider._get_voice_type("en-US-Unknown-Voice")
                self.assertEqual(voice_type, "gemini")
                mock_get_default_type.assert_called_once()

    def test_build_voice_params_basic(self):
        """Test building voice parameters from voice name."""
        with patch(
            "text_to_audio.services.google_tts_provider.get_google_tts_credentials"
        ) as mock_get_creds:
            mock_get_creds.return_value = self.mock_credentials
            with patch(
                "text_to_audio.services.google_tts_provider.service_account"
            ), patch(
                "text_to_audio.services.google_tts_provider.texttospeech_v1"
            ) as mock_tts_v1:
                provider = GoogleTTSProvider()

                mock_voice_params = MagicMock()
                mock_tts_v1.VoiceSelectionParams.return_value = mock_voice_params

                result = provider._build_voice_params(
                    "en-US-Journey-D", "gemini", None
                )

                # Verify VoiceSelectionParams called with correct language code
                mock_tts_v1.VoiceSelectionParams.assert_called_once_with(
                    language_code="en-US", name="en-US-Journey-D"
                )

                self.assertEqual(result, mock_voice_params)

    def test_build_voice_params_extracts_language_code(self):
        """Test language code extraction from voice name."""
        with patch(
            "text_to_audio.services.google_tts_provider.get_google_tts_credentials"
        ) as mock_get_creds:
            mock_get_creds.return_value = self.mock_credentials
            with patch(
                "text_to_audio.services.google_tts_provider.service_account"
            ), patch(
                "text_to_audio.services.google_tts_provider.texttospeech_v1"
            ) as mock_tts_v1:
                provider = GoogleTTSProvider()

                provider._build_voice_params("fr-FR-Neural2-B", "neural2", None)

                # Verify language code extracted correctly
                call_args = mock_tts_v1.VoiceSelectionParams.call_args[1]
                self.assertEqual(call_args["language_code"], "fr-FR")

    def test_build_voice_params_defaults_language_code(self):
        """Test language code defaults to en-US for invalid formats."""
        with patch(
            "text_to_audio.services.google_tts_provider.get_google_tts_credentials"
        ) as mock_get_creds:
            mock_get_creds.return_value = self.mock_credentials
            with patch(
                "text_to_audio.services.google_tts_provider.service_account"
            ), patch(
                "text_to_audio.services.google_tts_provider.texttospeech_v1"
            ) as mock_tts_v1:
                provider = GoogleTTSProvider()

                provider._build_voice_params("InvalidVoiceName", "gemini", None)

                # Verify language code defaults to en-US
                call_args = mock_tts_v1.VoiceSelectionParams.call_args[1]
                self.assertEqual(call_args["language_code"], "en-US")

    def test_get_audio_encoding_mp3(self):
        """Test audio encoding mapping for MP3."""
        with patch(
            "text_to_audio.services.google_tts_provider.get_google_tts_credentials"
        ) as mock_get_creds:
            mock_get_creds.return_value = self.mock_credentials
            with patch(
                "text_to_audio.services.google_tts_provider.service_account"
            ), patch(
                "text_to_audio.services.google_tts_provider.texttospeech_v1"
            ) as mock_tts_v1:
                provider = GoogleTTSProvider()

                encoding = provider._get_audio_encoding("mp3")

                self.assertEqual(encoding, mock_tts_v1.AudioEncoding.MP3)

    def test_get_audio_encoding_wav(self):
        """Test audio encoding mapping for WAV."""
        with patch(
            "text_to_audio.services.google_tts_provider.get_google_tts_credentials"
        ) as mock_get_creds:
            mock_get_creds.return_value = self.mock_credentials
            with patch(
                "text_to_audio.services.google_tts_provider.service_account"
            ), patch(
                "text_to_audio.services.google_tts_provider.texttospeech_v1"
            ) as mock_tts_v1:
                provider = GoogleTTSProvider()

                encoding = provider._get_audio_encoding("wav")

                self.assertEqual(encoding, mock_tts_v1.AudioEncoding.LINEAR16)

    def test_get_audio_encoding_defaults(self):
        """Test audio encoding defaults to LINEAR16 for unknown formats."""
        with patch(
            "text_to_audio.services.google_tts_provider.get_google_tts_credentials"
        ) as mock_get_creds:
            mock_get_creds.return_value = self.mock_credentials
            with patch(
                "text_to_audio.services.google_tts_provider.service_account"
            ), patch(
                "text_to_audio.services.google_tts_provider.texttospeech_v1"
            ) as mock_tts_v1:
                provider = GoogleTTSProvider()

                encoding = provider._get_audio_encoding("unknown")

                self.assertEqual(encoding, mock_tts_v1.AudioEncoding.LINEAR16)

    @patch("text_to_audio.services.google_tts_provider.get_google_tts_credentials")
    @patch("text_to_audio.services.google_tts_provider.service_account")
    @patch("text_to_audio.services.google_tts_provider.texttospeech_v1")
    def test_synthesize_speech_success(
        self, mock_tts_v1, mock_service_account, mock_get_creds
    ):
        """Test successful speech synthesis."""
        mock_get_creds.return_value = self.mock_credentials

        mock_credentials_obj = MagicMock()
        mock_service_account.Credentials.from_service_account_info.return_value = (
            mock_credentials_obj
        )

        # Mock client and response
        mock_client = MagicMock()
        mock_tts_v1.TextToSpeechClient.return_value = mock_client

        mock_response = MagicMock()
        mock_response.audio_content = b"synthesized_audio_data"
        mock_client.synthesize_speech.return_value = mock_response

        provider = GoogleTTSProvider()

        # Synthesize speech
        audio_bytes = provider.synthesize_speech(
            text="Hello world",
            voice_name="en-US-Journey-D",
            speed=1.0,
            output_format="wav",
        )

        # Verify result
        self.assertEqual(audio_bytes, b"synthesized_audio_data")

        # Verify API was called
        mock_client.synthesize_speech.assert_called_once()

    @patch("text_to_audio.services.google_tts_provider.get_google_tts_credentials")
    @patch("text_to_audio.services.google_tts_provider.service_account")
    @patch("text_to_audio.services.google_tts_provider.texttospeech_v1")
    def test_synthesize_speech_with_speed(
        self, mock_tts_v1, mock_service_account, mock_get_creds
    ):
        """Test speech synthesis includes speaking rate."""
        mock_get_creds.return_value = self.mock_credentials

        mock_credentials_obj = MagicMock()
        mock_service_account.Credentials.from_service_account_info.return_value = (
            mock_credentials_obj
        )

        mock_client = MagicMock()
        mock_tts_v1.TextToSpeechClient.return_value = mock_client

        mock_response = MagicMock()
        mock_response.audio_content = b"audio"
        mock_client.synthesize_speech.return_value = mock_response

        provider = GoogleTTSProvider()

        # Synthesize with custom speed
        provider.synthesize_speech(
            text="Test", voice_name="en-US-Journey-D", speed=1.5
        )

        # Verify AudioConfig includes speaking_rate
        call_args = mock_client.synthesize_speech.call_args[1]
        self.assertEqual(call_args["audio_config"].speaking_rate, 1.5)

    @patch("text_to_audio.services.google_tts_provider.get_google_tts_credentials")
    @patch("text_to_audio.services.google_tts_provider.service_account")
    @patch("text_to_audio.services.google_tts_provider.texttospeech_v1")
    def test_synthesize_speech_api_error(
        self, mock_tts_v1, mock_service_account, mock_get_creds
    ):
        """Test speech synthesis handles API errors."""
        mock_get_creds.return_value = self.mock_credentials

        mock_credentials_obj = MagicMock()
        mock_service_account.Credentials.from_service_account_info.return_value = (
            mock_credentials_obj
        )

        mock_client = MagicMock()
        mock_tts_v1.TextToSpeechClient.return_value = mock_client

        # Simulate API error
        mock_client.synthesize_speech.side_effect = Exception("API Error")

        provider = GoogleTTSProvider()

        with self.assertRaises(ValueError) as cm:
            provider.synthesize_speech(text="Test", voice_name="en-US-Journey-D")

        self.assertIn("Google TTS synthesis failed", str(cm.exception))
