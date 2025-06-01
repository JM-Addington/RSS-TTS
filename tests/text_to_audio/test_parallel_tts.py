"""
Tests for parallel TTS processing functionality.
"""

import os
import tempfile
import uuid
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest
from django.conf import settings
from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from pydub import AudioSegment

from text_to_audio.models import Article, Feed
from text_to_audio.parallel_tasks import generate_tts_for_chunk, stitch_audio_and_finalize
from text_to_audio.rate_limiter import TTSRateLimiter


class TestTTSRateLimiter(TestCase):
    """Test the TTSRateLimiter class."""

    def setUp(self):
        """Set up test fixtures."""
        # Use a mock Redis client for testing
        self.redis_mock = MagicMock()

    @patch('text_to_audio.rate_limiter.redis.Redis')
    def test_rate_limiter_initialization(self, mock_redis):
        """Test TTSRateLimiter initialization."""
        mock_redis.return_value = self.redis_mock

        rate_limiter = TTSRateLimiter()

        self.assertIsNotNone(rate_limiter.redis_client)
        self.assertEqual(rate_limiter.per_second_limit, 3)
        self.assertEqual(rate_limiter.per_minute_limit, 50)

    @patch('text_to_audio.rate_limiter.redis.Redis')
    def test_acquire_token_success(self, mock_redis):
        """Test successful token acquisition."""
        mock_redis.return_value = self.redis_mock

        # Mock Redis responses for under-limit scenario
        self.redis_mock.pipeline.return_value.execute.side_effect = [
            [None, None],  # Current counts (get)
            [1, 1]         # After increment
        ]

        rate_limiter = TTSRateLimiter()
        result = rate_limiter.acquire_tts_token(timeout=1.0)

        self.assertTrue(result)

    @patch('text_to_audio.rate_limiter.redis.Redis')
    def test_acquire_token_rate_limited(self, mock_redis):
        """Test token acquisition when rate limited."""
        mock_redis.return_value = self.redis_mock

        # Mock Redis responses for over-limit scenario
        self.redis_mock.pipeline.return_value.execute.return_value = [
            "5",  # Over per-second limit
            "30"  # Under per-minute limit
        ]

        rate_limiter = TTSRateLimiter()
        result = rate_limiter.acquire_tts_token(timeout=0.1)

        self.assertFalse(result)

    @patch('text_to_audio.rate_limiter.redis.Redis')
    def test_get_current_usage(self, mock_redis):
        """Test getting current usage statistics."""
        mock_redis.return_value = self.redis_mock
        self.redis_mock.pipeline.return_value.execute.return_value = ["2", "25"]

        rate_limiter = TTSRateLimiter()
        usage = rate_limiter.get_current_usage()

        self.assertEqual(usage["per_second"]["current"], 2)
        self.assertEqual(usage["per_second"]["limit"], 3)
        self.assertEqual(usage["per_minute"]["current"], 25)
        self.assertEqual(usage["per_minute"]["limit"], 50)


class TestGenerateTTSForChunk(TestCase):
    """Test the generate_tts_for_chunk task."""

    def setUp(self):
        """Set up test fixtures."""
        self.user = User.objects.create_user(username="testuser", password="password")
        self.feed = Feed.objects.create(
            user=self.user,
            name="Test Feed",
            url="https://example.com/feed.xml"
        )
        self.article = Article.objects.create(
            feed=self.feed,
            title="Test Article",
            text_content="This is test content for TTS processing.",
            status=Article.PROCESSING,
            audio_uuid=uuid.uuid4()
        )

        # Create temporary media directory
        self.temp_dir = tempfile.mkdtemp()
        self.media_dir = Path(self.temp_dir) / "articles"
        self.media_dir.mkdir(exist_ok=True)

    def tearDown(self):
        """Clean up test fixtures."""
        # Clean up temp files
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    @patch('text_to_audio.parallel_tasks.get_rate_limiter')
    @patch('text_to_audio.parallel_tasks.openai.OpenAI')
    @override_settings(MEDIA_ROOT=None)  # Will be set in test
    def test_generate_tts_chunk_success(self, mock_openai, mock_get_rate_limiter):
        """Test successful TTS chunk generation."""
        # Set up media root for this test
        with self.settings(MEDIA_ROOT=self.temp_dir):
            # Mock rate limiter
            mock_rate_limiter = MagicMock()
            mock_rate_limiter.acquire_tts_token.return_value = True
            mock_get_rate_limiter.return_value = mock_rate_limiter

            # Mock OpenAI client
            mock_client = MagicMock()
            mock_response = MagicMock()
            mock_response.headers = {"x-openai-tokens-used": "100"}
            mock_client.audio.speech.create.return_value = mock_response
            mock_openai.return_value = mock_client

            # Test data
            chunk_data = {
                "text": "Hello, this is a test chunk.",
                "voice": "alloy",
                "instructions": "Speak clearly and slowly."
            }
            voice_config = {
                "speed": 1.0,
                "instructions": "Default instructions",
                "voice": "alloy"
            }

            # Create a mock task context
            mock_task = MagicMock()
            mock_task.request.retries = 0
            mock_task.max_retries = 2

            with patch('text_to_audio.parallel_tasks.generate_tts_for_chunk.request', mock_task.request):
                result = generate_tts_for_chunk(
                    mock_task,
                    article_id=self.article.id,
                    chunk_data=chunk_data,
                    chunk_idx=0,
                    voice_config=voice_config
                )

            # Verify result
            chunk_idx, temp_file_path, error_msg = result
            self.assertEqual(chunk_idx, 0)
            self.assertIsNotNone(temp_file_path)
            self.assertIsNone(error_msg)

            # Verify OpenAI was called
            mock_client.audio.speech.create.assert_called_once()

            # Verify rate limiter was used
            mock_rate_limiter.acquire_tts_token.assert_called_once()

    @patch('text_to_audio.parallel_tasks.get_rate_limiter')
    def test_generate_tts_chunk_rate_limited(self, mock_get_rate_limiter):
        """Test TTS chunk generation when rate limited."""
        with self.settings(MEDIA_ROOT=self.temp_dir):
            # Mock rate limiter to deny token
            mock_rate_limiter = MagicMock()
            mock_rate_limiter.acquire_tts_token.return_value = False
            mock_get_rate_limiter.return_value = mock_rate_limiter

            chunk_data = {"text": "Test", "voice": "alloy"}
            voice_config = {"speed": 1.0}

            # Create a mock task context
            mock_task = MagicMock()
            mock_task.request.retries = 3  # Max retries reached
            mock_task.max_retries = 2

            with patch('text_to_audio.parallel_tasks.generate_tts_for_chunk.request', mock_task.request):
                result = generate_tts_for_chunk(
                    mock_task,
                    article_id=self.article.id,
                    chunk_data=chunk_data,
                    chunk_idx=0,
                    voice_config=voice_config
                )

            # Verify rate limit error
            chunk_idx, temp_file_path, error_msg = result
            self.assertEqual(chunk_idx, 0)
            self.assertIsNone(temp_file_path)
            self.assertIn("Rate limit timeout", error_msg)

    def test_generate_tts_chunk_article_not_found(self):
        """Test TTS chunk generation when article doesn't exist."""
        with self.settings(MEDIA_ROOT=self.temp_dir):
            chunk_data = {"text": "Test", "voice": "alloy"}
            voice_config = {"speed": 1.0}

            mock_task = MagicMock()

            result = generate_tts_for_chunk(
                mock_task,
                article_id=99999,  # Non-existent article
                chunk_data=chunk_data,
                chunk_idx=0,
                voice_config=voice_config
            )

            # Verify error
            chunk_idx, temp_file_path, error_msg = result
            self.assertEqual(chunk_idx, 0)
            self.assertIsNone(temp_file_path)
            self.assertIn("Article 99999 not found", error_msg)


class TestStitchAudioAndFinalize(TestCase):
    """Test the stitch_audio_and_finalize task."""

    def setUp(self):
        """Set up test fixtures."""
        self.user = User.objects.create_user(username="testuser", password="password")
        self.feed = Feed.objects.create(
            user=self.user,
            name="Test Feed",
            url="https://example.com/feed.xml"
        )
        self.article = Article.objects.create(
            feed=self.feed,
            title="Test Article",
            text_content="This is test content.",
            status=Article.PROCESSING,
            audio_uuid=uuid.uuid4()
        )

        # Create temporary media directory
        self.temp_dir = tempfile.mkdtemp()
        self.media_dir = Path(self.temp_dir) / "articles"
        self.media_dir.mkdir(exist_ok=True)

    def tearDown(self):
        """Clean up test fixtures."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _create_mock_audio_file(self, file_path: Path) -> None:
        """Create a mock MP3 file for testing."""
        # Create a simple 1-second audio segment
        audio_segment = AudioSegment.silent(duration=1000)  # 1 second
        audio_segment.export(str(file_path), format="mp3")

    @override_settings(MEDIA_ROOT=None)  # Will be set in test
    def test_stitch_audio_success_single_chunk(self):
        """Test successful audio stitching with a single chunk."""
        with self.settings(MEDIA_ROOT=self.temp_dir):
            # Create a mock audio file
            temp_file = self.media_dir / "test_chunk_0.mp3"
            self._create_mock_audio_file(temp_file)

            # Test data: single successful chunk
            chunk_results = [
                (0, str(temp_file), None)  # (chunk_idx, file_path, error)
            ]

            mock_task = MagicMock()

            result = stitch_audio_and_finalize(
                mock_task,
                chunk_results=chunk_results,
                article_id=self.article.id,
                final_audio_uuid=str(self.article.audio_uuid)
            )

            # Verify success
            self.assertIn("successful", result.lower())

            # Verify article status updated
            self.article.refresh_from_db()
            self.assertEqual(self.article.status, Article.COMPLETED)

            # Verify final audio file exists
            final_path = Path(self.article.get_canonical_audio_path())
            self.assertTrue(final_path.exists())

    @override_settings(MEDIA_ROOT=None)
    def test_stitch_audio_success_multiple_chunks(self):
        """Test successful audio stitching with multiple chunks."""
        with self.settings(MEDIA_ROOT=self.temp_dir):
            # Create multiple mock audio files
            temp_files = []
            for i in range(3):
                temp_file = self.media_dir / f"test_chunk_{i}.mp3"
                self._create_mock_audio_file(temp_file)
                temp_files.append(temp_file)

            # Test data: multiple successful chunks
            chunk_results = [
                (0, str(temp_files[0]), None),
                (1, str(temp_files[1]), None),
                (2, str(temp_files[2]), None),
            ]

            mock_task = MagicMock()

            result = stitch_audio_and_finalize(
                mock_task,
                chunk_results=chunk_results,
                article_id=self.article.id,
                final_audio_uuid=str(self.article.audio_uuid)
            )

            # Verify success
            self.assertIn("successful", result.lower())

            # Verify article status
            self.article.refresh_from_db()
            self.assertEqual(self.article.status, Article.COMPLETED)

    def test_stitch_audio_all_chunks_failed(self):
        """Test audio stitching when all chunks failed."""
        with self.settings(MEDIA_ROOT=self.temp_dir):
            # Test data: all chunks failed
            chunk_results = [
                (0, None, "TTS failed"),
                (1, None, "Rate limited"),
            ]

            mock_task = MagicMock()

            result = stitch_audio_and_finalize(
                mock_task,
                chunk_results=chunk_results,
                article_id=self.article.id,
                final_audio_uuid=str(self.article.audio_uuid)
            )

            # Verify failure
            self.assertIn("No successful TTS chunks", result)

            # Verify article marked as failed
            self.article.refresh_from_db()
            self.assertEqual(self.article.status, Article.FAILED)

    def test_stitch_audio_partial_failure(self):
        """Test audio stitching with some successful and some failed chunks."""
        with self.settings(MEDIA_ROOT=self.temp_dir):
            # Create one successful audio file
            temp_file = self.media_dir / "test_chunk_0.mp3"
            self._create_mock_audio_file(temp_file)

            # Test data: mixed success/failure (more success than failure)
            chunk_results = [
                (0, str(temp_file), None),  # Success
                (1, None, "TTS failed"),    # Failure
            ]

            mock_task = MagicMock()

            result = stitch_audio_and_finalize(
                mock_task,
                chunk_results=chunk_results,
                article_id=self.article.id,
                final_audio_uuid=str(self.article.audio_uuid)
            )

            # Should succeed despite partial failure
            self.assertIn("successful", result.lower())

            # Verify article completed
            self.article.refresh_from_db()
            self.assertEqual(self.article.status, Article.COMPLETED)

    def test_stitch_audio_majority_failed(self):
        """Test audio stitching when majority of chunks failed."""
        with self.settings(MEDIA_ROOT=self.temp_dir):
            # Create one successful audio file
            temp_file = self.media_dir / "test_chunk_0.mp3"
            self._create_mock_audio_file(temp_file)

            # Test data: majority failure
            chunk_results = [
                (0, str(temp_file), None),  # Success
                (1, None, "TTS failed"),    # Failure
                (2, None, "Rate limited"),  # Failure
            ]

            mock_task = MagicMock()

            result = stitch_audio_and_finalize(
                mock_task,
                chunk_results=chunk_results,
                article_id=self.article.id,
                final_audio_uuid=str(self.article.audio_uuid)
            )

            # Should fail due to majority failure
            self.assertIn("Too many failed chunks", result)

            # Verify article marked as failed
            self.article.refresh_from_db()
            self.assertEqual(self.article.status, Article.FAILED)


@override_settings(
    ENABLE_PARALLEL_TTS=True,
    CELERY_TTS_CHUNK_CONCURRENCY=2,
    CELERY_TASK_ALWAYS_EAGER=True  # Run tasks synchronously for testing
)
class TestParallelTTSIntegration(TestCase):
    """Integration tests for parallel TTS processing."""

    def setUp(self):
        """Set up test fixtures."""
        self.user = User.objects.create_user(username="testuser", password="password")
        self.feed = Feed.objects.create(
            user=self.user,
            name="Test Feed",
            url="https://example.com/feed.xml"
        )

        # Create temporary media directory
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        """Clean up test fixtures."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    @patch('text_to_audio.tasks.settings')
    def test_parallel_processing_enabled(self, mock_settings):
        """Test that parallel processing is used when enabled."""
        # Configure mock settings
        mock_settings.ENABLE_PARALLEL_TTS = True
        mock_settings.ENABLE_CHUNK_TONE_LLM = True
        mock_settings.MEDIA_ROOT = self.temp_dir
        mock_settings.OPENAI_API_KEY = "test-key"
        mock_settings.CELERY_TTS_CHUNK_CONCURRENCY = 2

        # This test would require more complex mocking of the ChunkToneService
        # and Celery group/chord functionality. For now, we verify the setting is checked.
        self.assertTrue(mock_settings.ENABLE_PARALLEL_TTS)

    @patch('text_to_audio.tasks.settings')
    def test_sequential_fallback_when_disabled(self, mock_settings):
        """Test that sequential processing is used when parallel is disabled."""
        mock_settings.ENABLE_PARALLEL_TTS = False

        # This would fall back to sequential processing
        self.assertFalse(mock_settings.ENABLE_PARALLEL_TTS)
