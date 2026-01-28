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
        with (
            patch("appconfig.utils.get_google_tts_api_key") as mock_api_key,
            patch("appconfig.utils.get_google_tts_credentials") as mock_creds,
        ):
            mock_api_key.return_value = "test-api-key"
            mock_creds.return_value = None

            # Mock the Google Cloud client
            with (
                patch(
                    "google.api_core.client_options.ClientOptions"
                ) as mock_client_opts,
                patch(
                    "google.cloud.texttospeech_v1.TextToSpeechClient"
                ) as mock_tts_client,
            ):
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
        with (
            patch("appconfig.utils.get_google_tts_api_key") as mock_api_key,
            patch("appconfig.utils.get_google_tts_credentials") as mock_creds,
        ):
            mock_api_key.return_value = None
            mock_creds.return_value = None

            from text_to_audio.services.google_tts_provider import GoogleTTSProvider

            with self.assertRaises(ValueError) as cm:
                GoogleTTSProvider()

            self.assertIn("Google TTS credentials not configured", str(cm.exception))

    def test_init_with_dict_credentials(self):
        """Test GoogleTTSProvider initializes with dict credentials."""
        with (
            patch("appconfig.utils.get_google_tts_api_key") as mock_api_key,
            patch("appconfig.utils.get_google_tts_credentials") as mock_creds,
            patch(
                "google.oauth2.service_account.Credentials.from_service_account_info"
            ) as mock_from_sa,
            patch("google.cloud.texttospeech_v1.TextToSpeechClient") as mock_tts_client,
        ):
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

        with (
            patch("appconfig.utils.get_google_tts_api_key") as mock_api_key,
            patch("appconfig.utils.get_google_tts_credentials") as mock_creds,
            patch(
                "google.oauth2.service_account.Credentials.from_service_account_info"
            ) as mock_from_sa,
            patch("google.cloud.texttospeech_v1.TextToSpeechClient") as mock_tts_client,
        ):
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
        with (
            patch("appconfig.utils.get_google_tts_api_key") as mock_api_key,
            patch("appconfig.utils.get_google_tts_credentials") as mock_creds,
        ):
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
        """Test successful speech synthesis with WAV wrapping."""
        provider, mock_client = self._create_provider_with_mocks()

        # Create fake PCM data (LINEAR16 returns raw PCM without headers)
        mock_response = MagicMock()
        mock_response.audio_content = b"\x00\x00" * 100  # Simulated raw PCM
        mock_client.synthesize_speech.return_value = mock_response

        # Synthesize speech (use Neural2 voice for simpler test)
        audio_bytes = provider.synthesize_speech(
            text="Hello world",
            voice_name="en-US-Neural2-A",
            speed=1.0,
            output_format="wav",
        )

        # Verify result has WAV header (RIFF) since we wrap LINEAR16 in WAV container
        self.assertTrue(audio_bytes.startswith(b"RIFF"))

        # Verify API was called
        mock_client.synthesize_speech.assert_called_once()

    def test_synthesize_speech_mp3_no_wrap(self):
        """Test MP3 output is not wrapped in WAV container."""
        provider, mock_client = self._create_provider_with_mocks()

        # MP3 data with typical header
        mp3_data = b"\xff\xfb\x90\x00" + b"\x00" * 100
        mock_response = MagicMock()
        mock_response.audio_content = mp3_data
        mock_client.synthesize_speech.return_value = mock_response

        audio_bytes = provider.synthesize_speech(
            text="Hello world",
            voice_name="en-US-Neural2-A",
            output_format="mp3",
        )

        # Verify MP3 data is returned as-is (not wrapped)
        self.assertEqual(audio_bytes, mp3_data)

    def test_synthesize_speech_wav_with_headers_not_rewrapped(self):
        """Test WAV data with existing RIFF header is not re-wrapped."""
        provider, mock_client = self._create_provider_with_mocks()

        # WAV data that already has RIFF header (per Google Cloud TTS docs)
        wav_data = b"RIFF\x00\x00\x00\x00WAVEfmt " + b"\x00" * 100
        mock_response = MagicMock()
        mock_response.audio_content = wav_data
        mock_client.synthesize_speech.return_value = mock_response

        audio_bytes = provider.synthesize_speech(
            text="Hello world",
            voice_name="en-US-Neural2-A",
            output_format="wav",
        )

        # Verify WAV data is returned as-is (not re-wrapped)
        self.assertEqual(audio_bytes, wav_data)

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


class WrapPcmInWavTest(TestCase):
    """Test the wrap_pcm_in_wav helper function."""

    def test_wrap_pcm_creates_valid_wav(self):
        """Test that wrap_pcm_in_wav creates valid WAV with RIFF header."""
        from text_to_audio.audio_utils import wrap_pcm_in_wav

        # Create some fake PCM data (16-bit samples)
        pcm_data = b"\x00\x01\x02\x03" * 100

        wav_bytes = wrap_pcm_in_wav(pcm_data)

        # Verify RIFF header
        self.assertTrue(wav_bytes.startswith(b"RIFF"))
        # Verify WAVE format marker at byte 8
        self.assertEqual(wav_bytes[8:12], b"WAVE")

    def test_wrap_pcm_with_custom_sample_rate(self):
        """Test WAV wrapping with custom sample rate."""
        from text_to_audio.audio_utils import wrap_pcm_in_wav
        import wave
        import io

        pcm_data = b"\x00\x00" * 48000  # 1 second at 48kHz

        wav_bytes = wrap_pcm_in_wav(pcm_data, sample_rate=48000)

        # Parse the WAV to verify sample rate
        with wave.open(io.BytesIO(wav_bytes), "rb") as wav_file:
            self.assertEqual(wav_file.getframerate(), 48000)

    def test_wrap_pcm_default_sample_rate(self):
        """Test WAV wrapping uses 24000 Hz sample rate by default (Google TTS)."""
        from text_to_audio.audio_utils import wrap_pcm_in_wav
        import wave
        import io

        pcm_data = b"\x00\x00" * 24000  # 1 second at 24kHz

        wav_bytes = wrap_pcm_in_wav(pcm_data)

        # Parse the WAV to verify default sample rate
        with wave.open(io.BytesIO(wav_bytes), "rb") as wav_file:
            self.assertEqual(wav_file.getframerate(), 24000)
            self.assertEqual(wav_file.getnchannels(), 1)  # Mono
            self.assertEqual(wav_file.getsampwidth(), 2)  # 16-bit


class IsValidWavTest(TestCase):
    """Test the is_valid_wav helper function."""

    def testis_valid_wav_returns_true_for_wav(self):
        """Test is_valid_wav returns True for valid WAV data."""
        from text_to_audio.audio_utils import is_valid_wav

        wav_data = b"RIFF\x00\x00\x00\x00WAVEfmt data"

        self.assertTrue(is_valid_wav(wav_data))

    def testis_valid_wav_returns_false_for_raw_pcm(self):
        """Test is_valid_wav returns False for raw PCM data."""
        from text_to_audio.audio_utils import is_valid_wav

        pcm_data = b"\x00\x00\x01\x00\x02\x00"

        self.assertFalse(is_valid_wav(pcm_data))

    def testis_valid_wav_returns_false_for_empty_data(self):
        """Test is_valid_wav returns False for empty or short data."""
        from text_to_audio.audio_utils import is_valid_wav

        self.assertFalse(is_valid_wav(b""))
        self.assertFalse(is_valid_wav(b"RI"))  # Too short
        self.assertFalse(is_valid_wav(b"RIF"))  # Too short

    def testis_valid_wav_returns_false_for_non_wav_riff(self):
        """Test is_valid_wav returns False for non-WAV RIFF containers (AVI, WebP)."""
        from text_to_audio.audio_utils import is_valid_wav

        # AVI file header (RIFF but not WAVE)
        avi_data = b"RIFF\x00\x00\x00\x00AVI LIST"
        self.assertFalse(is_valid_wav(avi_data))

        # WebP file header (RIFF but not WAVE)
        webp_data = b"RIFF\x00\x00\x00\x00WEBPVP8 "
        self.assertFalse(is_valid_wav(webp_data))

    def testis_valid_wav_returns_false_for_short_riff_header(self):
        """Test is_valid_wav returns False when RIFF header is too short for WAVE check."""
        from text_to_audio.audio_utils import is_valid_wav

        # Has RIFF but not enough bytes to check WAVE marker
        short_riff = b"RIFF\x00\x00\x00\x00WAV"  # 11 bytes, missing last byte of WAVE
        self.assertFalse(is_valid_wav(short_riff))


class WrapPcmEdgeCasesTest(TestCase):
    """Test edge cases for wrap_pcm_in_wav helper function."""

    def test_wrap_pcm_handles_empty_data(self):
        """Test wrap_pcm_in_wav handles empty PCM data gracefully."""
        from text_to_audio.audio_utils import wrap_pcm_in_wav

        # Should not raise an exception, but return a valid (empty) WAV
        wav_bytes = wrap_pcm_in_wav(b"")

        # Should still have valid WAV header
        self.assertTrue(wav_bytes.startswith(b"RIFF"))
        self.assertEqual(wav_bytes[8:12], b"WAVE")

    def test_wrap_pcm_handles_tiny_data(self):
        """Test wrap_pcm_in_wav handles very small PCM data."""
        from text_to_audio.audio_utils import wrap_pcm_in_wav

        # Single sample (2 bytes for 16-bit audio)
        tiny_data = b"\x00\x00"
        wav_bytes = wrap_pcm_in_wav(tiny_data)

        self.assertTrue(wav_bytes.startswith(b"RIFF"))
        self.assertEqual(wav_bytes[8:12], b"WAVE")
