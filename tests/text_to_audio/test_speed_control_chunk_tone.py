"""Tests for speed control in ChunkTone path.

This module contains regression tests for Critical Item 2 - Speed control lost in primary (ChunkTone) path.
It ensures that the resolved speed is properly propagated to every chunk in the ChunkTone path.
"""

import shutil
from pathlib import Path
from unittest.mock import MagicMock, patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from text_to_audio.models import Article, Feed
from text_to_audio.tasks import process_article

User = get_user_model()

# Use a temporary media root for tests
TEST_MEDIA_ROOT = Path(settings.BASE_DIR) / "test_media_speed_control"


@override_settings(
    MEDIA_ROOT=TEST_MEDIA_ROOT,
    OPENAI_API_KEY="test_api_key",
    ENABLE_CHUNK_TONE_LLM=True,  # Enable ChunkTone path
)
@patch("text_to_audio.tasks.openai.OpenAI")
class SpeedControlChunkToneTests(TestCase):
    """Tests for speed control in ChunkTone path."""

    @staticmethod
    def create_dummy_file_side_effect(path_arg, *args, **kwargs):
        """Create a dummy file for testing purposes."""
        Path(path_arg).parent.mkdir(parents=True, exist_ok=True)
        with open(path_arg, "wb") as f:
            f.write(b"dummy audio data for testing purposes")
        return None

    def setUp(self):
        """Set up test data and environment for each test."""
        if TEST_MEDIA_ROOT.exists():
            shutil.rmtree(TEST_MEDIA_ROOT)
        TEST_MEDIA_ROOT.mkdir(parents=True, exist_ok=True)

        self.user = User.objects.create_user(username="testuser", password="password")
        self.feed = Feed.objects.create(user=self.user, name="Test Feed")

    def tearDown(self):
        """Clean up test data and environment after each test."""
        if TEST_MEDIA_ROOT.exists():
            shutil.rmtree(TEST_MEDIA_ROOT)

    @patch("text_to_audio.tasks.ChunkToneService")
    @patch("text_to_audio.tasks.AudioSegment.from_file")
    @patch("text_to_audio.tasks.AudioSegment.empty")
    def test_speed_control_propagated_to_chunk_tone_service(
        self,
        mock_audio_empty,
        mock_audio_from_file,
        MockChunkToneService,
        MockOpenAIClient,
    ):
        """Test that speed is properly propagated to all chunks in ChunkTone path."""
        # Create test articles with different speeds
        article_125 = Article.objects.create(
            feed=self.feed,
            title="Test Article 1.25x",
            text_content="This is test content for 1.25x speed article.",
            speed=1.25,
        )

        article_100 = Article.objects.create(
            feed=self.feed,
            title="Test Article 1.0x",
            text_content="This is test content for 1.0x speed article.",
            speed=1.0,
        )

        # Mock ChunkToneService
        mock_chunk_tone_service = MockChunkToneService.return_value

        # Create mock chunk payload with 2 chunks for each article
        from text_to_audio.schemas.chunk_tone import (
            ChunkData,
            ChunkTonePayload,
            TTSVoice,
        )

        mock_payload_125 = ChunkTonePayload(
            chunks=[
                ChunkData(text="This is test content", voice=TTSVoice(voice="alloy")),
                ChunkData(
                    text="for 1.25x speed article.", voice=TTSVoice(voice="echo")
                ),
            ]
        )

        mock_payload_100 = ChunkTonePayload(
            chunks=[
                ChunkData(text="This is test content", voice=TTSVoice(voice="alloy")),
                ChunkData(text="for 1.0x speed article.", voice=TTSVoice(voice="echo")),
            ]
        )

        # Configure mock to return different payloads based on call
        call_count = 0

        def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return mock_payload_125
            else:
                return mock_payload_100

        mock_chunk_tone_service.get_payload.side_effect = side_effect

        # Mock OpenAI TTS calls
        mock_openai_instance = MockOpenAIClient.return_value
        mock_speech_create = mock_openai_instance.audio.speech.create

        mock_tts_response = MagicMock()
        mock_tts_response.usage = MagicMock(total_tokens=50)
        mock_tts_response.stream_to_file.side_effect = (
            self.create_dummy_file_side_effect
        )
        mock_speech_create.return_value = mock_tts_response

        # Mock audio processing
        mock_audio_segment = MagicMock()
        mock_audio_segment.set_frame_rate.return_value = mock_audio_segment
        mock_audio_segment.export.side_effect = self.create_dummy_file_side_effect
        mock_audio_from_file.return_value = mock_audio_segment

        from unittest.mock import PropertyMock

        combined_audio = MagicMock()
        type(combined_audio).duration_seconds = PropertyMock(return_value=10.0)
        combined_audio.set_frame_rate.return_value = combined_audio
        combined_audio.export.side_effect = self.create_dummy_file_side_effect
        combined_audio.__iadd__.return_value = combined_audio
        mock_audio_empty.return_value = combined_audio

        # Mock content analysis and voice configuration to avoid interference
        with patch(
            "text_to_audio.tasks.ContentAnalysisService"
        ) as MockContentAnalysisService, patch(
            "text_to_audio.tasks.VoiceConfigurationService"
        ), patch(
            "text_to_audio.tasks._save_openai_usage_stats"
        ):

            # Configure ContentAnalysisService to return None to skip multi-voice analysis
            mock_analysis_instance = MockContentAnalysisService.return_value
            mock_analysis_instance.analyze_content.return_value = None

            # Process first article (1.25x speed)
            result_125 = process_article(article_125.id)

            # Process second article (1.0x speed)
            result_100 = process_article(article_100.id)

        # Verify both articles processed successfully
        self.assertEqual(
            result_125, f"Article {article_125.id} processed successfully."
        )
        self.assertEqual(
            result_100, f"Article {article_100.id} processed successfully."
        )

        # Verify all TTS calls were made (2 chunks per article = 4 total calls)
        self.assertEqual(mock_speech_create.call_count, 4)

        # Get all TTS calls
        tts_calls = mock_speech_create.call_args_list

        # First 2 calls should be for article_125 (speed 1.25)
        for i in range(2):
            call_kwargs = tts_calls[i][1]
            self.assertEqual(
                call_kwargs["speed"],
                1.25,
                f"Call {i+1} should have speed 1.25, got {call_kwargs['speed']}",
            )
            # Verify instructions parameter is passed
            self.assertIn("instructions", call_kwargs)
            self.assertIsInstance(call_kwargs["instructions"], str)
            self.assertTrue(len(call_kwargs["instructions"]) > 0)

        # Last 2 calls should be for article_100 (speed 1.0)
        for i in range(2, 4):
            call_kwargs = tts_calls[i][1]
            self.assertEqual(
                call_kwargs["speed"],
                1.0,
                f"Call {i+1} should have speed 1.0, got {call_kwargs['speed']}",
            )
            # Verify instructions parameter is passed
            self.assertIn("instructions", call_kwargs)
            self.assertIsInstance(call_kwargs["instructions"], str)
            self.assertTrue(len(call_kwargs["instructions"]) > 0)

    @patch("text_to_audio.tasks.ChunkToneService")
    @patch("text_to_audio.tasks.AudioSegment.from_file")
    @patch("text_to_audio.tasks.AudioSegment.empty")
    def test_speed_from_voice_parameters_prioritized(
        self,
        mock_audio_empty,
        mock_audio_from_file,
        MockChunkToneService,
        MockOpenAIClient,
    ):
        """Test that speed from voice_parameters takes priority over article.speed."""
        # Create article with speed in voice_parameters
        article = Article.objects.create(
            feed=self.feed,
            title="Test Article with voice_parameters",
            text_content="This is test content for voice_parameters speed test.",
            speed=1.0,  # Lower priority
            voice_parameters={"speed": 1.5},  # Higher priority
        )

        # Mock ChunkToneService
        mock_chunk_tone_service = MockChunkToneService.return_value

        from text_to_audio.schemas.chunk_tone import (
            ChunkData,
            ChunkTonePayload,
            TTSVoice,
        )

        mock_payload = ChunkTonePayload(
            chunks=[
                ChunkData(text="This is test content", voice=TTSVoice(voice="alloy")),
                ChunkData(
                    text="for voice_parameters speed test.",
                    voice=TTSVoice(voice="echo"),
                ),
            ]
        )
        mock_chunk_tone_service.get_payload.return_value = mock_payload

        # Mock OpenAI TTS calls
        mock_openai_instance = MockOpenAIClient.return_value
        mock_speech_create = mock_openai_instance.audio.speech.create

        mock_tts_response = MagicMock()
        mock_tts_response.usage = MagicMock(total_tokens=50)
        mock_tts_response.stream_to_file.side_effect = (
            self.create_dummy_file_side_effect
        )
        mock_speech_create.return_value = mock_tts_response

        # Mock audio processing
        mock_audio_segment = MagicMock()
        mock_audio_segment.set_frame_rate.return_value = mock_audio_segment
        mock_audio_segment.export.side_effect = self.create_dummy_file_side_effect
        mock_audio_from_file.return_value = mock_audio_segment

        from unittest.mock import PropertyMock

        combined_audio = MagicMock()
        type(combined_audio).duration_seconds = PropertyMock(return_value=10.0)
        combined_audio.set_frame_rate.return_value = combined_audio
        combined_audio.export.side_effect = self.create_dummy_file_side_effect
        combined_audio.__iadd__.return_value = combined_audio
        mock_audio_empty.return_value = combined_audio

        # Mock content analysis and voice configuration to avoid interference
        with patch(
            "text_to_audio.tasks.ContentAnalysisService"
        ) as MockContentAnalysisService, patch(
            "text_to_audio.tasks.VoiceConfigurationService"
        ), patch(
            "text_to_audio.tasks._save_openai_usage_stats"
        ):

            # Configure ContentAnalysisService to return None to skip multi-voice analysis
            mock_analysis_instance = MockContentAnalysisService.return_value
            mock_analysis_instance.analyze_content.return_value = None

            # Process article
            result = process_article(article.id)

        # Verify article processed successfully
        self.assertEqual(result, f"Article {article.id} processed successfully.")

        # Verify TTS calls were made
        self.assertEqual(mock_speech_create.call_count, 2)

        # Verify both calls used speed from voice_parameters (1.5, not 1.0)
        tts_calls = mock_speech_create.call_args_list
        for i, call in enumerate(tts_calls):
            call_kwargs = call[1]
            self.assertEqual(
                call_kwargs["speed"],
                1.5,
                f"Call {i+1} should use voice_parameters speed 1.5, got {call_kwargs['speed']}",
            )
            # Verify instructions parameter is passed
            self.assertIn("instructions", call_kwargs)
            self.assertIsInstance(call_kwargs["instructions"], str)
            self.assertTrue(len(call_kwargs["instructions"]) > 0)

    @patch("text_to_audio.tasks.ChunkToneService")
    @patch("text_to_audio.tasks.AudioSegment.from_file")
    @patch("text_to_audio.tasks.AudioSegment.empty")
    def test_speed_fallback_when_none_specified(
        self,
        mock_audio_empty,
        mock_audio_from_file,
        MockChunkToneService,
        MockOpenAIClient,
    ):
        """Test that speed falls back to 1.0 when not specified."""
        # Create article with no speed specified
        article = Article.objects.create(
            feed=self.feed,
            title="Test Article no speed",
            text_content="This is test content with no speed specified.",
            # speed=None (default)
        )

        # Mock ChunkToneService
        mock_chunk_tone_service = MockChunkToneService.return_value

        from text_to_audio.schemas.chunk_tone import (
            ChunkData,
            ChunkTonePayload,
            TTSVoice,
        )

        mock_payload = ChunkTonePayload(
            chunks=[
                ChunkData(text="This is test content", voice=TTSVoice(voice="alloy")),
                ChunkData(
                    text="with no speed specified.", voice=TTSVoice(voice="echo")
                ),
            ]
        )
        mock_chunk_tone_service.get_payload.return_value = mock_payload

        # Mock OpenAI TTS calls
        mock_openai_instance = MockOpenAIClient.return_value
        mock_speech_create = mock_openai_instance.audio.speech.create

        mock_tts_response = MagicMock()
        mock_tts_response.usage = MagicMock(total_tokens=50)
        mock_tts_response.stream_to_file.side_effect = (
            self.create_dummy_file_side_effect
        )
        mock_speech_create.return_value = mock_tts_response

        # Mock audio processing
        mock_audio_segment = MagicMock()
        mock_audio_segment.set_frame_rate.return_value = mock_audio_segment
        mock_audio_segment.export.side_effect = self.create_dummy_file_side_effect
        mock_audio_from_file.return_value = mock_audio_segment

        from unittest.mock import PropertyMock

        combined_audio = MagicMock()
        type(combined_audio).duration_seconds = PropertyMock(return_value=10.0)
        combined_audio.set_frame_rate.return_value = combined_audio
        combined_audio.export.side_effect = self.create_dummy_file_side_effect
        combined_audio.__iadd__.return_value = combined_audio
        mock_audio_empty.return_value = combined_audio

        # Mock content analysis and voice configuration to avoid interference
        with patch(
            "text_to_audio.tasks.ContentAnalysisService"
        ) as MockContentAnalysisService, patch(
            "text_to_audio.tasks.VoiceConfigurationService"
        ), patch(
            "text_to_audio.tasks._save_openai_usage_stats"
        ):

            # Configure ContentAnalysisService to return None to skip multi-voice analysis
            mock_analysis_instance = MockContentAnalysisService.return_value
            mock_analysis_instance.analyze_content.return_value = None

            # Process article
            result = process_article(article.id)

        # Verify article processed successfully
        self.assertEqual(result, f"Article {article.id} processed successfully.")

        # Verify TTS calls were made
        self.assertEqual(mock_speech_create.call_count, 2)

        # Verify both calls used default speed 1.0
        tts_calls = mock_speech_create.call_args_list
        for i, call in enumerate(tts_calls):
            call_kwargs = call[1]
            self.assertEqual(
                call_kwargs["speed"],
                1.0,
                f"Call {i+1} should use default speed 1.0, got {call_kwargs['speed']}",
            )
            # Verify instructions parameter is passed
            self.assertIn("instructions", call_kwargs)
            self.assertIsInstance(call_kwargs["instructions"], str)
            self.assertTrue(len(call_kwargs["instructions"]) > 0)
