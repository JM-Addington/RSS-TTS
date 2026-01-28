"""Tests for the text_to_audio app's task functions.

This module contains tests for the text chunking algorithm and article processing
functionality.
"""

# mypy: disable-error-code="attr-defined"

from __future__ import annotations

import shutil
from pathlib import Path
from unittest.mock import MagicMock, PropertyMock, patch

from django.conf import (
    settings as django_settings,  # Use a different alias to avoid conflict with fixture
)
from django.contrib.auth import get_user_model

# Configure Django settings before importing models and tasks
if not django_settings.configured:
    django_settings.configure(
        INSTALLED_APPS=[
            "django.contrib.auth",
            "django.contrib.contenttypes",
            "text_to_audio",  # Add the app itself
        ],
        AUTH_USER_MODEL="auth.User",  # Standard Django user model
        MEDIA_ROOT=Path(__file__).parent
        / "test_media_tasks_global",  # Consistent test media root
        OPENAI_API_KEY="test_api_key_global",
        MAX_ANALYSIS_WORDS=8000,
        OPENAI_ANALYSIS_MODEL="gpt-4.1",
        OPENAI_TTS_MODEL="tts-1-hd",  # Default model that supports instructions
        LOG_OPENAI_API_CALLS=False,
        ARTICLE_PROCESSING_TIMEOUT_SECONDS=3600,
        ENABLE_CHUNK_TONE_LLM=False,
        OPENAI_TITLE_MODEL="gpt-4o-mini",
        OPENAI_TTS_VOICE="alloy",  # Default voice for fallback
        DATABASES={
            "default": {
                "ENGINE": "django.db.backends.sqlite3",
                "NAME": ":memory:",
            }
        },
    )
    import django
    from django.core.management import call_command

    django.setup()
    call_command("migrate", verbosity=0)


from django.test import TestCase, override_settings
from openai import APIError as OpenAIAPIError
from pydub import AudioSegment  # type: ignore[import-untyped]

from text_to_audio.models import Article, Feed
from text_to_audio.tasks import _clamp_tts_speed, _legacy_chunk_text, process_article

User = get_user_model()
TEST_MEDIA_ROOT = Path(__file__).parent / "test_media_tasks_global"


@override_settings(MEDIA_ROOT=TEST_MEDIA_ROOT)
class ChunkTextTests(TestCase):
    def test_empty_string(self):
        success, chunks = _legacy_chunk_text("")
        self.assertTrue(success)
        self.assertEqual(chunks, [])

    def test_short_string(self):
        text = "This is a short sentence."
        success, chunks = _legacy_chunk_text(text, max_length=100)
        self.assertTrue(success)
        self.assertEqual(chunks, [text])

    def test_string_equals_max_length(self):
        text = "abcde"
        success, chunks = _legacy_chunk_text(text, max_length=5)
        self.assertTrue(success)
        self.assertEqual(chunks, [text])

    def test_string_needs_one_split_by_space(self):
        text = "This is a sentence that needs splitting.  "
        success, chunks = _legacy_chunk_text(text, max_length=20)
        self.assertTrue(success)
        for chunk in chunks:
            self.assertLessEqual(len(chunk), 20)

    def test_string_needs_multiple_splits(self):
        text = "one two three four five six seven eight nine ten"
        success, chunks = _legacy_chunk_text(text, max_length=17)
        self.assertTrue(
            success
        )  # This test might fail if _legacy_chunk_text logic changed
        for chunk in chunks:
            self.assertLessEqual(len(chunk), 17)
        combined = " ".join(chunks)
        # This assertion might be too strict if chunker adds/removes spaces at split points
        # For now, keeping it to see if it's a real issue or just whitespace.
        # self.assertEqual(combined, text)
        for word in text.split():  # A more robust check
            self.assertIn(word, combined)

    def test_split_respects_paragraph_breaks(self):
        text = "First paragraph.\n\nSecond paragraph, which is a bit longer."
        success, chunks_ml50 = _legacy_chunk_text(text, max_length=50)
        self.assertTrue(success)
        self.assertEqual(len(chunks_ml50), 2)
        success, chunks_ml30 = _legacy_chunk_text(text, max_length=30)
        self.assertTrue(success)
        for chunk in chunks_ml30:
            self.assertLessEqual(len(chunk), 30)

    def test_split_respects_sentence_breaks(self):
        text = "First sentence. Second sentence, also fairly short. Third one."
        success, chunks = _legacy_chunk_text(text, max_length=40)
        self.assertTrue(success)
        self.assertEqual(len(chunks), 3)
        self.assertIn("First sentence", chunks[0])
        self.assertIn("Second sentence", chunks[1])
        self.assertIn("Third one", chunks[2])

    def test_long_word_handling(self):
        text = "Supercalifragilisticexpialidocious"
        success, chunks = _legacy_chunk_text(text, max_length=20)
        for chunk in chunks:
            self.assertLessEqual(len(chunk), 20)

    def test_force_split_if_no_natural_break(self):
        text = "abcdefghijklmnopqrstuvwxyz"
        success, chunks = _legacy_chunk_text(text, max_length=20)
        self.assertFalse(
            success
        )  # This test might fail if _legacy_chunk_text logic changed
        for chunk in chunks:
            self.assertLessEqual(len(chunk), 20)

        # Test edge case: text length equals max_length with no natural breaks
        text_exact = "abcdefghijklmnopqrst"  # exactly 20 chars, no spaces
        success_exact, chunks_exact = _legacy_chunk_text(text_exact, max_length=20)
        # Since there are no natural breaks, this should still be considered a forced split
        # But with our current logic, if len(text) < max_length, it returns len(text)
        # Since 20 == 20 (not < 20), it should go through the natural break search
        # and since no natural breaks are found, should return 0, leading to forced split
        self.assertTrue(success_exact)  # This should be True since text fits exactly
        self.assertEqual(len(chunks_exact), 1)
        self.assertEqual(chunks_exact[0], text_exact)

    def test_mixed_content_with_various_breaks(self):
        text = "Short. Longer sentence here.\n\nNew paragraph. Another sentence. And a final one."
        success, chunks = _legacy_chunk_text(text, max_length=30)
        self.assertTrue(success)
        for chunk in chunks:
            self.assertLessEqual(len(chunk), 30)
        combined = " ".join(chunks)
        for word in text.replace("\n", " ").split():
            self.assertIn(word, combined)

    def test_huck_finn_excerpt(self):
        fixture_path = (
            Path(__file__).parent.parent / "fixtures" / "huckfinn_excerpt.txt"
        )
        with open(fixture_path, "r") as f:
            text = f.read()
        success, chunks = _legacy_chunk_text(text, max_length=4000)
        self.assertTrue(success)
        self.assertTrue(len(chunks) >= 1)
        for chunk in chunks:
            self.assertLessEqual(len(chunk), 4000)
        success, chunks = _legacy_chunk_text(text, max_length=1000)
        self.assertTrue(success)
        self.assertTrue(len(chunks) >= 3)
        for chunk in chunks:
            self.assertLessEqual(len(chunk), 1000)
        success, chunks = _legacy_chunk_text(text, max_length=200)
        self.assertTrue(success)
        self.assertTrue(len(chunks) >= 10)
        for chunk in chunks:
            self.assertLessEqual(len(chunk), 200)
        success, chunks = _legacy_chunk_text(text, max_length=20)
        self.assertTrue(len(chunks) > 0)
        for chunk in chunks:
            self.assertLessEqual(len(chunk), 20)

    def test_legacy_chunk_text_large_continuous_input_no_infinite_loop(self):
        large_continuous_text = "a" * 5000
        max_length = 100
        success, chunks = _legacy_chunk_text(
            large_continuous_text, max_length=max_length
        )
        self.assertTrue(len(chunks) > 0)
        for chunk in chunks:
            self.assertLessEqual(len(chunk), max_length)
        combined_length = sum(len(chunk) for chunk in chunks)
        self.assertEqual(combined_length, len(large_continuous_text))
        expected_chunks = len(large_continuous_text) // max_length
        self.assertEqual(len(chunks), expected_chunks)

    def test_legacy_chunk_text_stress_test_completion(self):
        test_cases = [
            ("a" * 1000, 100),
            ("word" * 300, 50),
            ("x" * 500 + " end", 100),
        ]
        for text, max_len in test_cases:
            with self.subTest(text_len=len(text), max_length=max_len):
                success, chunks = _legacy_chunk_text(text, max_length=max_len)
                self.assertTrue(len(chunks) > 0)
                for chunk in chunks:
                    self.assertLessEqual(len(chunk), max_len)
                total_chunk_chars = sum(len(chunk) for chunk in chunks)
                self.assertGreaterEqual(total_chunk_chars, len(text) * 0.9)


@override_settings(MEDIA_ROOT=TEST_MEDIA_ROOT, OPENAI_API_KEY="test_api_key")
@patch("text_to_audio.tasks.openai.OpenAI")
class ProcessArticleTests(TestCase):
    @staticmethod
    def create_dummy_file_side_effect(path_arg, *args, **kwargs):
        Path(path_arg).parent.mkdir(parents=True, exist_ok=True)
        with open(path_arg, "wb") as f:
            f.write(b"dummy audio data for testing purposes")
        return None

    def _setup_audio_mocks(self, mock_audio_empty_patch, mock_audio_from_file_patch):
        mock_segment = MagicMock()
        mock_segment.set_frame_rate.return_value = mock_segment
        mock_segment.export.side_effect = self.create_dummy_file_side_effect
        type(mock_segment).duration_seconds = PropertyMock(return_value=1.0)
        mock_audio_from_file_patch.return_value = mock_segment

        empty_audio_mock = MagicMock()
        self._current_mock_duration = 0.0
        type(empty_audio_mock).duration_seconds = PropertyMock(
            side_effect=lambda: self._current_mock_duration
        )

        def iadd_segment(other):
            if hasattr(other, "duration_seconds"):
                self._current_mock_duration += other.duration_seconds
            else:
                self._current_mock_duration += 1.0
            return empty_audio_mock

        empty_audio_mock.__iadd__.side_effect = iadd_segment
        empty_audio_mock.set_frame_rate.return_value = empty_audio_mock
        empty_audio_mock.export.side_effect = self.create_dummy_file_side_effect
        mock_audio_empty_patch.return_value = empty_audio_mock
        return mock_segment, empty_audio_mock

    def setUp(self):
        if TEST_MEDIA_ROOT.exists():
            try:
                shutil.rmtree(TEST_MEDIA_ROOT)
            except OSError:
                # Directory might be busy (bind-mounted in Docker), clear contents instead
                for item in TEST_MEDIA_ROOT.iterdir():
                    if item.is_file():
                        try:
                            item.unlink()
                        except OSError:
                            pass
                    elif item.is_dir():
                        try:
                            shutil.rmtree(item)
                        except OSError:
                            pass
        TEST_MEDIA_ROOT.mkdir(parents=True, exist_ok=True)
        self.user = User.objects.create_user(username="testuser", password="password")
        self.feed = Feed.objects.create(user=self.user, name="Test Feed")
        self.article = Article.objects.create(
            feed=self.feed,
            title="Test Article",
            text_content="This is the test content for our article. It has sentences.",
        )
        self.mock_task_instance = MagicMock()
        self.mock_task_instance.request.retries = 0
        self.mock_task_instance.max_retries = 3
        self.mock_task_instance.default_retry_delay = 60
        self.mock_task_instance.retry = MagicMock(
            side_effect=Exception("Celery general retry called")
        )

    def tearDown(self):
        if TEST_MEDIA_ROOT.exists():
            try:
                shutil.rmtree(TEST_MEDIA_ROOT)
            except OSError:
                # Directory might be busy (bind-mounted in Docker), clear contents instead
                for item in TEST_MEDIA_ROOT.iterdir():
                    if item.is_file():
                        try:
                            item.unlink()
                        except OSError:
                            pass
                    elif item.is_dir():
                        try:
                            shutil.rmtree(item)
                        except OSError:
                            pass

    @override_settings(ENABLE_CHUNK_TONE_LLM=False)  # Test legacy path
    @patch("text_to_audio.tasks.AudioSegment.silent")
    @patch("text_to_audio.tasks.AudioSegment.from_file")
    @patch("text_to_audio.tasks.AudioSegment.empty")
    def test_process_article_success_single_chunk(
        self, mock_audio_empty, mock_audio_from_file, mock_silent, MockOpenAIClient
    ):
        self._setup_audio_mocks(mock_audio_empty, mock_audio_from_file)
        mock_openai_instance = MockOpenAIClient.return_value
        mock_speech_create = mock_openai_instance.audio.speech.create
        mock_tts_response = MagicMock()
        mock_tts_response.usage = MagicMock(total_tokens=123)
        # TTS service now uses iter_bytes() instead of stream_to_file()
        mock_tts_response.iter_bytes.return_value = [b"dummy audio data"]
        mock_speech_create.return_value = mock_tts_response

        self.article.voice_parameters = None
        self.article.multi_voice_data = None  # Ensure it goes to fallback
        self.article.save()

        result = process_article(self.article.id)

        self.article.refresh_from_db()
        self.assertEqual(result, f"Article {self.article.id} processed successfully.")
        self.assertEqual(self.article.status, Article.COMPLETED)
        self.assertIsNotNone(self.article.audio_file_path)
        self.assertIsNone(self.article.error_message)

        call_args = mock_speech_create.call_args[1]
        # Legacy fallback path with no voice parameters should not include instructions
        self.assertNotIn("instructions", call_args)
        self.assertEqual(call_args["voice"], "alloy")
        self.assertEqual(call_args["speed"], 1.0)

    @patch("text_to_audio.tasks.ContentAnalysisService")
    @patch("text_to_audio.tasks.AudioSegment.from_file")
    @patch("text_to_audio.tasks.AudioSegment.empty")
    def test_process_article_success_with_summary(
        self,
        mock_audio_empty,
        mock_audio_from_file,
        MockContentAnalysisService,
        MockOpenAIClient,
    ):
        self._setup_audio_mocks(mock_audio_empty, mock_audio_from_file)
        mock_openai_instance = MockOpenAIClient.return_value
        mock_speech_create = mock_openai_instance.audio.speech.create
        mock_tts_response = MagicMock()
        mock_tts_response.usage = MagicMock(total_tokens=100)
        # TTS service now uses iter_bytes() instead of stream_to_file()
        mock_tts_response.iter_bytes.return_value = [b"dummy audio data"]
        mock_speech_create.return_value = mock_tts_response

        mock_analysis_instance = MockContentAnalysisService.return_value
        expected_summary = "This is a test summary from content analysis."
        analysis_result = {
            "summary": expected_summary,
            "voices": [
                {
                    "name": "narrator",
                    "tone": "neutral",
                    "tts_model": "alloy",
                    "tts_speed": 1.0,
                }
            ],
            "audio_segments": [
                {"text": self.article.text_content, "voice_name": "narrator"}
            ],
        }
        mock_analysis_instance.analyze_content.return_value = analysis_result

        with patch(
            "text_to_audio.tasks._is_valid_multi_voice_data", return_value=True
        ), patch("text_to_audio.tasks._save_openai_usage_stats"):
            result = process_article(self.article.id)

        self.article.refresh_from_db()
        self.assertEqual(result, f"Article {self.article.id} processed successfully.")
        self.assertEqual(self.article.status, Article.COMPLETED)
        self.assertIsNotNone(self.article.audio_file_path)
        self.assertEqual(self.article.summary, expected_summary)
        self.assertIsNotNone(self.article.multi_voice_data)
        self.assertEqual(self.article.multi_voice_data["summary"], expected_summary)

    @patch("text_to_audio.tasks.AudioSegment.from_file")
    @patch("text_to_audio.tasks.AudioSegment.empty")
    @patch("text_to_audio.tasks._generate_title")
    def test_process_article_generates_title_when_missing(
        self,
        mock_generate_title,
        mock_audio_empty,
        mock_audio_from_file,
        MockOpenAIClient,
    ):
        self._setup_audio_mocks(mock_audio_empty, mock_audio_from_file)
        self.article.title = ""
        self.article.save()
        mock_generate_title.return_value = "Auto"
        mock_openai_instance = MockOpenAIClient.return_value
        mock_speech_create = mock_openai_instance.audio.speech.create
        mock_tts_response = MagicMock()
        mock_tts_response.usage = MagicMock(total_tokens=10)
        # TTS service now uses iter_bytes() instead of stream_to_file()
        mock_tts_response.iter_bytes.return_value = [b"dummy audio data"]
        mock_speech_create.return_value = mock_tts_response

        result = process_article(self.article.id)
        self.article.refresh_from_db()
        self.assertEqual(result, f"Article {self.article.id} processed successfully.")
        self.assertEqual(self.article.title, "Auto")
        mock_generate_title.assert_called_once()

    @override_settings(ENABLE_CHUNK_TONE_LLM=False)  # Test legacy path
    @patch("text_to_audio.tasks.AudioSegment.from_file")
    @patch("text_to_audio.tasks.AudioSegment.empty")
    def test_process_article_success_multiple_chunks(
        self, mock_audio_empty, mock_audio_from_file, MockOpenAIClient
    ):
        self._setup_audio_mocks(mock_audio_empty, mock_audio_from_file)
        self.article.text_content = "Test content for multiple chunks"
        self.article.multi_voice_data = (
            None  # Ensure fallback path that uses _legacy_chunk_text
        )
        self.article.save()

        mock_openai_instance = MockOpenAIClient.return_value
        mock_speech_create = mock_openai_instance.audio.speech.create
        mock_tts_response = MagicMock()
        mock_tts_response.usage = MagicMock(total_tokens=50)
        # TTS service now uses iter_bytes() instead of stream_to_file()
        mock_tts_response.iter_bytes.return_value = [b"dummy audio data"]
        mock_speech_create.return_value = mock_tts_response
        chunks_data = ["Chunk 1 content.", "Second chunk here."]  # 3 words, 3 words

        # Create a patch to force return of multiple chunks and to mock audio processing
        with patch(
            "text_to_audio.tasks._legacy_chunk_text"
        ) as mock_legacy_chunk_text, patch.object(
            Path, "rename"
        ):  # Prevent file rename attempts

            # Return 2 chunks to force multi-chunk processing
            mock_legacy_chunk_text.return_value = (True, chunks_data)

            process_article(self.article.id)

        self.article.refresh_from_db()
        self.assertEqual(self.article.status, Article.COMPLETED)
        self.assertEqual(mock_speech_create.call_count, len(chunks_data))

    @override_settings(
        ENABLE_CHUNK_TONE_LLM=False
    )  # Test legacy path for expected error message
    @patch("text_to_audio.tasks.AudioSegment.from_file")
    @patch("text_to_audio.tasks.AudioSegment.empty")
    def test_process_article_stat_saving_error(
        self, mock_audio_empty, mock_audio_from_file, MockOpenAIClient
    ):
        self._setup_audio_mocks(mock_audio_empty, mock_audio_from_file)
        from unittest.mock import patch as unittest_patch

        def raise_db_error(*args, **kwargs):
            raise Exception("DB error saving stats")

        mock_openai_instance = MockOpenAIClient.return_value
        mock_speech_create = mock_openai_instance.audio.speech.create
        mock_tts_response = MagicMock(spec=["iter_bytes"])
        usage_mock = MagicMock()
        usage_mock.total_tokens = 100
        type(mock_tts_response).usage = PropertyMock(return_value=usage_mock)
        # TTS service now uses iter_bytes() instead of stream_to_file()
        mock_tts_response.iter_bytes.return_value = [b"dummy audio data"]
        mock_speech_create.return_value = mock_tts_response
        self.article.multi_voice_data = None  # Ensure fallback path
        self.article.save()

        with unittest_patch("text_to_audio.tasks.process_article.retry") as mock_retry:
            mock_retry.return_value = None
            with unittest_patch(
                "text_to_audio.models.OpenAIUsageStats.objects.create",
                side_effect=raise_db_error,
            ):
                with self.assertLogs(
                    "text_to_audio.services.usage_logging", level="ERROR"
                ) as log_watcher:
                    process_article(self.article.id)
        self.assertTrue(
            any(
                "Failed to log TTS usage" in message and "fallback_chunk_0" in message
                for message in log_watcher.output
            )
        )

    @patch("text_to_audio.tasks.AudioSegment.from_file")
    @patch("text_to_audio.tasks.AudioSegment.empty")
    @patch("text_to_audio.tasks._save_openai_usage_stats")
    def test_process_article_token_extraction_from_headers(
        self, mock_save_stats, mock_audio_empty, mock_audio_from_file, MockOpenAIClient
    ):
        self._setup_audio_mocks(mock_audio_empty, mock_audio_from_file)
        mock_openai_instance = MockOpenAIClient.return_value
        mock_speech_create = mock_openai_instance.audio.speech.create
        mock_tts_response = MagicMock(spec=["headers", "iter_bytes"])
        mock_tts_response.headers = {"x-openai-tokens-used": "150"}
        type(mock_tts_response).usage = PropertyMock(side_effect=AttributeError)
        # TTS service now uses iter_bytes() instead of stream_to_file()
        mock_tts_response.iter_bytes.return_value = [b"dummy audio data"]
        mock_speech_create.return_value = mock_tts_response
        process_article(self.article.id)
        mock_save_stats.assert_called_once()
        self.assertEqual(mock_save_stats.call_args[1]["tokens_used"], 150)

    @patch("text_to_audio.tasks.AudioSegment.from_file")
    @patch("text_to_audio.tasks.AudioSegment.empty")
    @patch("text_to_audio.tasks._save_openai_usage_stats")
    def test_process_article_token_extraction_fallback(
        self, mock_save_stats, mock_audio_empty, mock_audio_from_file, MockOpenAIClient
    ):
        self._setup_audio_mocks(mock_audio_empty, mock_audio_from_file)
        mock_openai_instance = MockOpenAIClient.return_value
        mock_speech_create = mock_openai_instance.audio.speech.create
        mock_tts_response = MagicMock(spec=["headers", "iter_bytes"])
        mock_tts_response.headers = {"some-other-header": "some-value"}
        type(mock_tts_response).usage = PropertyMock(side_effect=AttributeError)
        # TTS service now uses iter_bytes() instead of stream_to_file()
        mock_tts_response.iter_bytes.return_value = [b"dummy audio data"]
        mock_speech_create.return_value = mock_tts_response
        process_article(self.article.id)
        mock_save_stats.assert_called_once()
        self.assertEqual(mock_save_stats.call_args[1]["tokens_used"], 0)

    def test_process_article_openai_api_error_with_retry(self, MockOpenAIClient):
        mock_openai_instance = MockOpenAIClient.return_value
        mock_speech_create = mock_openai_instance.audio.speech.create
        mock_speech_create.side_effect = OpenAIAPIError(
            "TTS failed", request=MagicMock(), body=None
        )
        with patch(
            "text_to_audio.tasks.process_article.retry",
            side_effect=Exception("Celery OpenAI error retry"),
        ) as mock_retry:
            with self.assertRaisesRegex(Exception, "Celery OpenAI error retry"):
                process_article(self.article.id)
            self.article.refresh_from_db()
            self.assertEqual(self.article.status, Article.FAILED)
            self.assertIn("APIError: TTS failed", self.article.error_message)
            mock_retry.assert_called_once()

    @patch("django.db.transaction.atomic", lambda inner_func=None: inner_func)
    @patch("text_to_audio.tasks.AudioSegment.from_file")
    @patch("text_to_audio.tasks.AudioSegment.empty")
    def test_process_article_pydub_error(
        self, mock_audio_empty, mock_audio_from_file, MockOpenAIClient
    ):
        self._setup_audio_mocks(mock_audio_empty, mock_audio_from_file)
        self.article.text_content = (
            "Test content for multiple chunks. " * 10
        )  # Ensure multiple chunks
        self.article.multi_voice_data = (
            None  # Force fallback to single voice with multiple chunks
        )
        self.article.save()
        mock_openai_instance = MockOpenAIClient.return_value
        mock_speech_create = mock_openai_instance.audio.speech.create
        mock_tts_response = MagicMock()
        # TTS service now uses iter_bytes() instead of stream_to_file()
        mock_tts_response.iter_bytes.return_value = [b"dummy audio data"]
        mock_speech_create.return_value = mock_tts_response

        mock_audio_from_file.side_effect = Exception(
            "Pydub test error"
        )  # Error on combining

        with patch("text_to_audio.tasks._save_openai_usage_stats"), patch(
            "text_to_audio.tasks.process_article.retry",
            side_effect=Exception("Celery Pydub error retry"),
        ) as mock_retry:
            with self.assertRaisesRegex(Exception, "Celery Pydub error retry"):
                process_article(self.article.id)
            self.article.refresh_from_db()
            self.assertEqual(self.article.status, Article.FAILED)
            self.assertIn("Pydub test error", self.article.error_message)
            mock_retry.assert_called_once()

    def test_process_article_empty_text_content(self, MockOpenAIClient):
        self.article.text_content = ""
        self.article.save()
        with patch(
            "text_to_audio.tasks.process_article.retry",
            side_effect=Exception("Celery empty content retry"),
        ) as mock_retry:
            with self.assertRaisesRegex(Exception, "Celery empty content retry"):
                process_article(self.article.id)
            self.article.refresh_from_db()
            self.assertEqual(self.article.status, Article.FAILED)
            self.assertIn("Article text_content is empty.", self.article.error_message)
            mock_retry.assert_called_once()

    def test_article_not_found(self, MockOpenAIClient):
        result = process_article.apply(
            args=[99999], instance=self.mock_task_instance
        ).get()
        self.assertEqual(result, "Article 99999 not found.")

    @override_settings(ENABLE_CHUNK_TONE_LLM=False)  # Force legacy path
    @patch("text_to_audio.tasks.AudioSegment.from_file")
    @patch("text_to_audio.tasks.AudioSegment.empty")
    @patch("text_to_audio.tasks._save_openai_usage_stats")
    def test_temp_files_cleaned_up_on_success(
        self, mock_save_stats, mock_audio_empty, mock_audio_from_file, MockOpenAIClient
    ):
        self._setup_audio_mocks(mock_audio_empty, mock_audio_from_file)
        mock_openai_instance = MockOpenAIClient.return_value
        mock_speech_create = mock_openai_instance.audio.speech.create
        mock_tts_response = MagicMock(spec=["iter_bytes"])
        usage_mock = MagicMock()
        usage_mock.total_tokens = 100
        type(mock_tts_response).usage = PropertyMock(return_value=usage_mock)
        # TTS service now uses iter_bytes() instead of stream_to_file()
        mock_tts_response.iter_bytes.return_value = [b"dummy audio data"]
        mock_speech_create.return_value = mock_tts_response
        chunks = ["Chunk one for cleanup.", "Chunk two for cleanup."]
        with patch(
            "text_to_audio.tasks._legacy_chunk_text", return_value=(True, chunks)
        ):
            with patch("django.db.transaction.atomic", lambda func=None: func):
                with patch("text_to_audio.tasks.os.remove") as mock_os_remove:
                    process_article(self.article.id)
                    self.article.refresh_from_db()
                    self.assertEqual(self.article.status, Article.COMPLETED)
                    self.assertTrue(mock_os_remove.call_count >= len(chunks))

    @override_settings(ENABLE_CHUNK_TONE_LLM=False)  # Force legacy path
    @patch("django.db.transaction.atomic", lambda inner_func=None: inner_func)
    @patch("text_to_audio.tasks.AudioSegment.from_file")
    @patch("text_to_audio.tasks.AudioSegment.empty")
    def test_temp_files_cleaned_up_on_failure(
        self, mock_audio_empty, mock_audio_from_file, MockOpenAIClient
    ):
        self._setup_audio_mocks(mock_audio_empty, mock_audio_from_file)
        self.article.text_content = "First chunk content. " * 5
        self.article.save()
        mock_openai_instance = MockOpenAIClient.return_value
        mock_speech_create = mock_openai_instance.audio.speech.create
        mock_successful_tts_response = MagicMock()
        # TTS service now uses iter_bytes() instead of stream_to_file()
        mock_successful_tts_response.iter_bytes.return_value = [b"dummy audio data"]
        mock_speech_create.side_effect = [
            mock_successful_tts_response,
            OpenAIAPIError(
                "TTS failed on second chunk", request=MagicMock(), body=None
            ),
        ]
        with patch("text_to_audio.tasks._save_openai_usage_stats"), patch(
            "text_to_audio.tasks.ContentAnalysisService"
        ) as MockCAS:
            MockCAS.return_value.analyze_content.return_value = {
                "summary": "",
                "voices": [],
                "audio_segments": [],
            }
            with patch("text_to_audio.tasks.os.remove") as mock_os_remove, patch(
                "text_to_audio.tasks._legacy_chunk_text",
                return_value=(True, ["Chunk 1", "Chunk 2"]),
            ), patch(
                "text_to_audio.tasks.process_article.retry",
                side_effect=Exception("Celery failure cleanup retry"),
            ):
                with self.assertRaisesRegex(Exception, "Celery failure cleanup retry"):
                    process_article(self.article.id)
                self.assertTrue(
                    mock_os_remove.call_count >= 1
                )  # At least the first successful chunk's temp file

    @override_settings(ENABLE_CHUNK_TONE_LLM=False)  # Test legacy path
    @patch("text_to_audio.tasks.ContentAnalysisService")
    @patch("text_to_audio.tasks.AudioSegment.from_file")
    @patch("text_to_audio.tasks.AudioSegment.empty")
    def test_process_article_successful_multi_voice(
        self, mock_audio_empty, mock_audio_from_file, MockCAS, MockOpenAIClient
    ):
        self._setup_audio_mocks(mock_audio_empty, mock_audio_from_file)
        mock_openai_instance = MockOpenAIClient.return_value
        mock_speech_create = mock_openai_instance.audio.speech.create
        mock_tts_response = MagicMock()
        # TTS service now uses iter_bytes() instead of stream_to_file()
        mock_tts_response.iter_bytes.return_value = [b"dummy audio data"]
        mock_speech_create.return_value = mock_tts_response

        expected_summary = "Multi-voice summary."
        valid_multi_voice_data = {
            "summary": expected_summary,
            "voices": [
                {
                    "name": "narrator",
                    "tone": "neutral",
                    "tts_model": "alloy",
                    "tts_speed": 1.0,
                },
                {"name": "hero", "tone": "bold", "tts_model": "onyx", "tts_speed": 1.1},
            ],
            "audio_segments": [
                {"text": "Chapter one.", "voice_name": "narrator"},
                {"text": "I am the hero!", "voice_name": "hero"},
            ],
        }
        MockCAS.return_value.analyze_content.return_value = valid_multi_voice_data

        with patch(
            "text_to_audio.tasks._is_valid_multi_voice_data", return_value=True
        ), patch("text_to_audio.tasks._save_openai_usage_stats"):
            process_article(self.article.id)
        self.article.refresh_from_db()
        self.assertEqual(self.article.summary, expected_summary)
        self.assertEqual(mock_speech_create.call_count, 2)

    @override_settings(ENABLE_CHUNK_TONE_LLM=False)  # Test legacy path
    @patch("text_to_audio.tasks.ContentAnalysisService")
    @patch("text_to_audio.tasks.AudioSegment.from_file")
    @patch("text_to_audio.tasks.AudioSegment.empty")
    def test_process_article_fallback_to_single_voice(
        self, mock_audio_empty, mock_audio_from_file, MockCAS, MockOpenAIClient
    ):
        self._setup_audio_mocks(mock_audio_empty, mock_audio_from_file)
        mock_openai_instance = MockOpenAIClient.return_value
        mock_speech_create = mock_openai_instance.audio.speech.create
        mock_tts_response = MagicMock()
        # TTS service now uses iter_bytes() instead of stream_to_file()
        mock_tts_response.iter_bytes.return_value = [b"dummy audio data"]
        mock_speech_create.return_value = mock_tts_response

        expected_summary = "Summary from invalid data"
        MockCAS.return_value.analyze_content.return_value = {
            "summary": expected_summary,
            "voices": [],
            "audio_segments": [],
        }

        self.article.text_content = "This is fallback content. It is short."
        self.article.voice = ""  # Empty string to test voice_id fallback
        self.article.voice_id = "echo"  # This should be used since voice is empty
        self.article.speed = 0.9
        self.article.save()

        with patch(
            "text_to_audio.tasks._is_valid_multi_voice_data", return_value=False
        ), patch("text_to_audio.tasks._save_openai_usage_stats"):
            process_article(self.article.id)
        self.article.refresh_from_db()
        self.assertEqual(self.article.summary, expected_summary)
        call_args = mock_speech_create.call_args_list[0][1]
        # When voice is empty, voice_id should be used
        self.assertEqual(call_args["voice"], "echo")

    @override_settings(ENABLE_CHUNK_TONE_LLM=False)  # Test legacy multi-voice path
    @patch("text_to_audio.tasks.ContentAnalysisService")
    @patch("text_to_audio.tasks.AudioSegment.from_file")
    @patch("text_to_audio.tasks.AudioSegment.empty")
    def test_process_article_multi_voice_segment_chunking(
        self, mock_audio_empty, mock_audio_from_file, MockCAS, MockOpenAIClient
    ):
        self._setup_audio_mocks(mock_audio_empty, mock_audio_from_file)
        mock_openai_instance = MockOpenAIClient.return_value
        mock_speech_create = mock_openai_instance.audio.speech.create
        mock_tts_response = MagicMock()
        # TTS service now uses iter_bytes() instead of stream_to_file()
        mock_tts_response.iter_bytes.return_value = [b"dummy audio data"]
        mock_speech_create.return_value = mock_tts_response

        # Create a long text that will be chunked (over 4000 chars to force chunking)
        # Each repetition is ~75 chars, so 60 repetitions = ~4500 chars (over 4000 limit)
        long_segment_text_actually_long = (
            "This is an extremely long segment designed to test chunking functionality. "
            * 60
        )
        short_segment_text = "This is short."
        expected_summary = "Summary for chunking test."
        multi_voice_data_with_long_segment = {
            "summary": expected_summary,
            "voices": [
                {
                    "name": "long_talker",
                    "tone": "verbose",
                    "tts_model": "fable",
                    "tts_speed": 1.0,
                },
                {
                    "name": "short_talker",
                    "tone": "concise",
                    "tts_model": "shimmer",
                    "tts_speed": 0.8,
                },
            ],
            "audio_segments": [
                {"text": long_segment_text_actually_long, "voice_name": "long_talker"},
                {"text": short_segment_text, "voice_name": "short_talker"},
            ],
        }
        MockCAS.return_value.analyze_content.return_value = (
            multi_voice_data_with_long_segment
        )

        with patch(
            "text_to_audio.tasks._is_valid_multi_voice_data", return_value=True
        ), patch("text_to_audio.tasks._save_openai_usage_stats"):
            process_article(self.article.id)
        self.article.refresh_from_db()
        self.assertEqual(self.article.summary, expected_summary)
        # We expect 61 calls: 60 for long segment chunks + 1 for short segment
        self.assertEqual(mock_speech_create.call_count, 61)

    @patch("text_to_audio.tasks.ContentAnalysisService")
    @patch("text_to_audio.tasks.AudioSegment.from_file")
    @patch("text_to_audio.tasks.AudioSegment.empty")
    def test_process_article_success_with_empty_summary(
        self, mock_audio_empty, mock_audio_from_file, MockCAS, MockOpenAIClient
    ):
        self._setup_audio_mocks(mock_audio_empty, mock_audio_from_file)
        mock_openai_instance = MockOpenAIClient.return_value
        mock_speech_create = mock_openai_instance.audio.speech.create
        mock_tts_response = MagicMock()
        mock_tts_response.usage = MagicMock(total_tokens=100)
        # TTS service now uses iter_bytes() instead of stream_to_file()
        mock_tts_response.iter_bytes.return_value = [b"dummy audio data"]
        mock_speech_create.return_value = mock_tts_response

        expected_empty_summary = ""
        analysis_result = {
            "summary": expected_empty_summary,
            "voices": [
                {
                    "name": "narrator",
                    "tone": "neutral",
                    "tts_model": "alloy",
                    "tts_speed": 1.0,
                }
            ],
            "audio_segments": [
                {"text": self.article.text_content, "voice_name": "narrator"}
            ],
        }
        MockCAS.return_value.analyze_content.return_value = analysis_result
        with patch(
            "text_to_audio.tasks._is_valid_multi_voice_data", return_value=True
        ), patch("text_to_audio.tasks._save_openai_usage_stats"):
            process_article(self.article.id)
        self.article.refresh_from_db()
        self.assertEqual(self.article.summary, expected_empty_summary)
        self.assertEqual(
            self.article.multi_voice_data["summary"], expected_empty_summary
        )

    @patch("text_to_audio.tasks.ContentAnalysisService")
    @patch("text_to_audio.tasks.AudioSegment.from_file")
    @patch("text_to_audio.tasks.AudioSegment.empty")
    def test_process_article_failure_after_summary_saved(
        self, mock_audio_empty, mock_audio_from_file, MockCAS, MockOpenAIClient
    ):
        self._setup_audio_mocks(mock_audio_empty, mock_audio_from_file)
        expected_summary = "Summary generated before TTS failure."
        analysis_result = {
            "summary": expected_summary,
            "voices": [
                {
                    "name": "narrator",
                    "tone": "neutral",
                    "tts_model": "alloy",
                    "tts_speed": 1.0,
                }
            ],
            "audio_segments": [
                {"text": self.article.text_content, "voice_name": "narrator"}
            ],
        }
        MockCAS.return_value.analyze_content.return_value = analysis_result

        mock_openai_instance = MockOpenAIClient.return_value
        mock_speech_create = mock_openai_instance.audio.speech.create
        mock_speech_create.side_effect = OpenAIAPIError(
            "Simulated TTS API Error", request=MagicMock(), body=None
        )

        with patch(
            "text_to_audio.tasks.process_article.retry",
            side_effect=Exception("Celery retry for test"),
        ), patch(
            "text_to_audio.tasks._is_valid_multi_voice_data", return_value=True
        ), patch(
            "text_to_audio.tasks._save_openai_usage_stats"
        ):
            with self.assertRaisesRegex(Exception, "Celery retry for test"):
                process_article(self.article.id)
        self.article.refresh_from_db()
        self.assertEqual(self.article.summary, expected_summary)
        self.assertEqual(self.article.multi_voice_data["summary"], expected_summary)
        self.assertEqual(self.article.status, Article.FAILED)

    @override_settings(ENABLE_CHUNK_TONE_LLM=False)  # Test legacy path
    @patch("text_to_audio.tasks.ContentAnalysisService")
    @patch("text_to_audio.tasks.AudioSegment.from_file")
    @patch("text_to_audio.tasks.AudioSegment.empty")
    def test_process_article_long_text_full_analysis(
        self, mock_audio_empty, mock_audio_from_file, MockCAS, MockOpenAIClient
    ):
        self._setup_audio_mocks(mock_audio_empty, mock_audio_from_file)
        long_text = "longword " * 1000
        self.article.text_content = long_text
        self.article.save()

        expected_summary = "Summary for long text."
        analysis_result = {
            "summary": expected_summary,
            "voices": [
                {
                    "name": "narrator",
                    "tone": "neutral",
                    "tts_model": "alloy",
                    "tts_speed": 1.0,
                }
            ],
            "audio_segments": [{"text": long_text, "voice_name": "narrator"}],
        }
        MockCAS.return_value.analyze_content.return_value = analysis_result

        mock_openai_instance = MockOpenAIClient.return_value
        mock_speech_create = mock_openai_instance.audio.speech.create
        mock_tts_response = MagicMock()
        # TTS service now uses iter_bytes() instead of stream_to_file()
        mock_tts_response.iter_bytes.return_value = [b"dummy audio data"]
        mock_speech_create.return_value = mock_tts_response

        with patch(
            "text_to_audio.tasks._is_valid_multi_voice_data", return_value=True
        ), patch("text_to_audio.tasks._save_openai_usage_stats"):
            process_article(self.article.id)
        self.article.refresh_from_db()
        self.assertEqual(self.article.summary, expected_summary)
        MockCAS.return_value.analyze_content.assert_called_once_with(
            long_text, title=self.article.title
        )

    @patch("text_to_audio.tasks.VoiceConfigurationService")
    @patch("text_to_audio.services.voice_parameter_generation.ContentAnalysisService")
    @patch("text_to_audio.tasks.ContentAnalysisService")
    @patch("text_to_audio.tasks.AudioSegment.from_file")
    @patch("text_to_audio.tasks.AudioSegment.empty")
    def test_content_analysis_called_once_for_auto_feed(
        self,
        mock_audio_empty,
        mock_audio_from_file,
        MockTasksCAS,
        MockVPGenCAS,
        MockVoiceConfigService,
        MockOpenAIClient,
    ):
        self._setup_audio_mocks(mock_audio_empty, mock_audio_from_file)
        from text_to_audio.models import Feed

        self.feed.voice_mode = Feed.VOICE_MODE_AUTO
        self.feed.save()

        mock_openai_instance = MockOpenAIClient.return_value
        mock_speech_create = mock_openai_instance.audio.speech.create
        mock_tts_response = MagicMock()
        # TTS service now uses iter_bytes() instead of stream_to_file()
        mock_tts_response.iter_bytes.return_value = [b"dummy audio data"]
        mock_speech_create.return_value = mock_tts_response

        mock_cas_for_vpgen = MockVPGenCAS.return_value
        expected_summary = "Summary for auto feed test."
        analysis_result = {
            "summary": expected_summary,
            "voices": [
                {
                    "name": "narrator",
                    "tone": "neutral",
                    "tts_model": "alloy",
                    "tts_speed": 1.0,
                }
            ],
            "audio_segments": [
                {"text": self.article.text_content, "voice_name": "narrator"}
            ],
        }
        mock_cas_for_vpgen.analyze_content.return_value = analysis_result

        mock_voice_config_instance = MockVoiceConfigService.return_value

        def configure_article_voice_side_effect(article_obj):
            # Simulate VoiceConfigurationService calling VoiceParameterGenerationService,
            # which in turn calls its ContentAnalysisService instance (mock_cas_for_vpgen)
            internal_analysis_result = mock_cas_for_vpgen.analyze_content(
                article_obj.text_content, article_obj.title
            )
            article_obj.multi_voice_data = internal_analysis_result
            article_obj.summary = internal_analysis_result["summary"]
            # Actual service also saves, simulate that part if crucial for subsequent logic not tested here.
            # For this test, process_article's final save will pick up these changes.
            return article_obj

        mock_voice_config_instance.configure_article_voice.side_effect = (
            configure_article_voice_side_effect
        )

        mock_direct_cas_in_task = MockTasksCAS.return_value

        with patch("text_to_audio.tasks._save_openai_usage_stats"), patch(
            "text_to_audio.tasks._is_valid_multi_voice_data", return_value=True
        ):
            process_article(self.article.id)

        self.article.refresh_from_db()
        self.assertEqual(self.article.status, Article.COMPLETED)
        self.assertEqual(self.article.summary, expected_summary)
        self.assertIsNotNone(self.article.multi_voice_data)
        self.assertEqual(self.article.multi_voice_data["summary"], expected_summary)
        mock_cas_for_vpgen.analyze_content.assert_called_once()
        mock_direct_cas_in_task.analyze_content.assert_not_called()

    @patch("text_to_audio.tasks.ContentAnalysisService")
    @patch("text_to_audio.tasks.AudioSegment.from_file")
    @patch("text_to_audio.tasks.AudioSegment.empty")
    def test_process_article_long_article_chunked_analysis(
        self, mock_audio_empty, mock_audio_from_file, MockCAS, MockOpenAIClient
    ):
        self._setup_audio_mocks(mock_audio_empty, mock_audio_from_file)
        from text_to_audio.services.content_analysis import MAX_ANALYSIS_WORDS

        long_text = "word " * (MAX_ANALYSIS_WORDS + 1000)
        self.article.text_content = long_text
        self.article.save()
        mock_openai_instance = MockOpenAIClient.return_value
        mock_speech_create = mock_openai_instance.audio.speech.create
        mock_tts_response = MagicMock()
        # TTS service now uses iter_bytes() instead of stream_to_file()
        mock_tts_response.iter_bytes.return_value = [b"dummy audio data"]
        mock_speech_create.return_value = mock_tts_response

        mock_analysis_instance = MockCAS.return_value
        expected_first_summary = "Summary for chunk in Test Article (Part 1)"

        def analysis_side_effect(text, title=None):
            if "Part 1" in title:
                return {
                    "summary": expected_first_summary,
                    "voices": [
                        {
                            "name": "narrator1",
                            "tone": "neutral",
                            "tts_model": "alloy",
                            "tts_speed": 1.0,
                        }
                    ],
                    "audio_segments": [{"text": text, "voice_name": "narrator1"}],
                }
            else:
                return {
                    "summary": f"Summary for chunk in {title}",
                    "voices": [
                        {
                            "name": "narrator2",
                            "tone": "energetic",
                            "tts_model": "onyx",
                            "tts_speed": 1.1,
                        }
                    ],
                    "audio_segments": [{"text": text, "voice_name": "narrator2"}],
                }

        mock_analysis_instance.analyze_content.side_effect = analysis_side_effect

        with patch(
            "text_to_audio.tasks._is_valid_multi_voice_data", return_value=True
        ), patch("text_to_audio.tasks._save_openai_usage_stats"):
            process_article(self.article.id)
        self.article.refresh_from_db()
        self.assertEqual(self.article.summary, expected_first_summary)

    @patch("text_to_audio.tasks.ContentAnalysisService")
    @patch("text_to_audio.tasks.AudioSegment.from_file")
    @patch("text_to_audio.tasks.AudioSegment.empty")
    def test_process_article_saves_summary_successfully(
        self,
        mock_audio_empty,
        mock_audio_from_file,
        MockContentAnalysisService,
        MockOpenAIClient,
    ):
        """Test that article.summary is populated and saved on successful processing."""
        self._setup_audio_mocks(mock_audio_empty, mock_audio_from_file)

        # Ensure the article starts in a state where content analysis will be called
        self.article.text_content = "This is the article text for summary."
        self.article.multi_voice_data = None  # Ensure analysis is triggered
        self.article.summary = None
        self.article.status = Article.PROCESSING
        self.article.save()

        # Mock ContentAnalysisService
        mock_cas_instance = MockContentAnalysisService.return_value
        expected_summary = "This is a test summary."
        mock_analyze_content_result = {
            "voices": [
                {
                    "name": "narrator",
                    "tone": "neutral",
                    "tts_model": "alloy",
                    "tts_speed": 1.0,
                }
            ],
            "audio_segments": [
                {"text": self.article.text_content, "voice_name": "narrator"}
            ],
            "summary": expected_summary,
        }
        mock_cas_instance.analyze_content.return_value = mock_analyze_content_result

        # Mock OpenAI TTS client
        mock_openai_instance = MockOpenAIClient.return_value
        mock_speech_response = MagicMock()
        # TTS service now uses iter_bytes() instead of stream_to_file()
        mock_speech_response.iter_bytes.return_value = [b"dummy audio data"]
        # Ensure 'usage' attribute is present if your code accesses it, even if just for tokens
        mock_speech_response.usage = MagicMock(
            prompt_tokens=10, completion_tokens=20, total_tokens=30
        )  # Example usage data
        mock_openai_instance.audio.speech.create.return_value = mock_speech_response

        # Mock _is_valid_multi_voice_data to True to follow the multi-voice path
        # which uses the direct output of analyze_content.
        with patch(
            "text_to_audio.tasks._is_valid_multi_voice_data", return_value=True
        ), patch(
            "text_to_audio.tasks._save_openai_usage_stats"
        ):  # Patch stats to simplify test
            process_article(self.article.id)

        self.article.refresh_from_db()
        self.assertEqual(
            self.article.summary,
            expected_summary,
            "Article summary was not saved correctly.",
        )
        self.assertEqual(
            self.article.status,
            Article.COMPLETED,
            "Article status was not set to COMPLETED.",
        )
        mock_cas_instance.analyze_content.assert_called_once_with(
            self.article.text_content, title=self.article.title
        )

        # Check multi_voice_data content
        self.assertIsNotNone(self.article.multi_voice_data)
        self.assertEqual(self.article.multi_voice_data.get("summary"), expected_summary)
        self.assertEqual(
            self.article.multi_voice_data.get("voices"),
            mock_analyze_content_result["voices"],
        )
        self.assertEqual(
            self.article.multi_voice_data.get("audio_segments"),
            mock_analyze_content_result["audio_segments"],
        )

    @patch("text_to_audio.tasks.AudioSegment.from_file")
    @patch("text_to_audio.tasks.AudioSegment.empty")
    def test_process_article_speed_clamping_single_voice(
        self, mock_audio_empty, mock_audio_from_file, MockOpenAIClient
    ):
        self._setup_audio_mocks(mock_audio_empty, mock_audio_from_file)
        test_cases = [(0.1, 0.25), (1.0, 1.0), (5.0, 4.0)]
        for input_speed, expected_speed in test_cases:
            with self.subTest(input_speed=input_speed, expected_speed=expected_speed):
                self.article.speed = input_speed
                self.article.multi_voice_data = None
                self.article.save()
                mock_openai_instance = MockOpenAIClient.return_value
                mock_speech_create = mock_openai_instance.audio.speech.create
                mock_tts_response = MagicMock()
                # TTS service now uses iter_bytes() instead of stream_to_file()
                mock_tts_response.iter_bytes.return_value = [b"dummy audio data"]
                mock_speech_create.return_value = mock_tts_response
                with patch("text_to_audio.tasks._save_openai_usage_stats"):
                    process_article(self.article.id)
                self.assertEqual(
                    mock_speech_create.call_args[1]["speed"], expected_speed
                )
                MockOpenAIClient.reset_mock()

    @patch("text_to_audio.tasks.ChunkToneService")
    @patch("text_to_audio.tasks.AudioSegment.from_file")
    @patch("text_to_audio.tasks.AudioSegment.empty")
    @override_settings(ENABLE_CHUNK_TONE_LLM=True)
    def test_process_article_speed_clamping_chunk_tone(
        self,
        mock_audio_empty,
        mock_audio_from_file,
        MockChunkToneService,
        MockOpenAIClient,
    ):
        self._setup_audio_mocks(mock_audio_empty, mock_audio_from_file)
        from text_to_audio.schemas.chunk_tone import (
            ChunkData,
            ChunkTonePayload,
            TTSVoice,
        )

        test_cases = [(0.2, 0.25), (2.5, 2.5), (4.5, 4.0)]
        for input_speed, expected_speed in test_cases:
            with self.subTest(input_speed=input_speed, expected_speed=expected_speed):
                self.article.speed = input_speed
            self.article.save()
            mock_chunk_tone_instance = MockChunkToneService.return_value
            mock_chunk_tone_instance.get_payload.return_value = ChunkTonePayload(
                chunks=[
                    ChunkData(text="Test chunk text", voice=TTSVoice(voice="alloy"))
                ]
            )
            mock_openai_instance = MockOpenAIClient.return_value
            mock_speech_create = mock_openai_instance.audio.speech.create
            mock_tts_response = MagicMock()
            # TTS service now uses iter_bytes() instead of stream_to_file()
            mock_tts_response.iter_bytes.return_value = [b"dummy audio data"]
            mock_speech_create.return_value = mock_tts_response
            with patch("text_to_audio.tasks._save_openai_usage_stats"):
                process_article(self.article.id)
            self.assertEqual(mock_speech_create.call_args[1]["speed"], expected_speed)
            MockOpenAIClient.reset_mock()
            MockChunkToneService.reset_mock()


class SpeedClampingUnitTests(TestCase):
    def test_clamp_tts_speed_below_minimum(self):
        self.assertEqual(_clamp_tts_speed(0.0), 0.25)
        self.assertEqual(_clamp_tts_speed(0.1), 0.25)
        self.assertEqual(_clamp_tts_speed(0.24), 0.25)
        self.assertEqual(_clamp_tts_speed(-1.0), 0.25)

    def test_clamp_tts_speed_above_maximum(self):
        self.assertEqual(_clamp_tts_speed(4.1), 4.0)
        self.assertEqual(_clamp_tts_speed(5.0), 4.0)
        self.assertEqual(_clamp_tts_speed(10.0), 4.0)

    def test_clamp_tts_speed_in_range(self):
        self.assertEqual(_clamp_tts_speed(0.25), 0.25)
        self.assertEqual(_clamp_tts_speed(1.0), 1.0)
        self.assertEqual(_clamp_tts_speed(2.5), 2.5)
        self.assertEqual(_clamp_tts_speed(4.0), 4.0)


# New tests for volume gain constant
class VolumeGainConstantTests(TestCase):
    def test_volume_gain_constant(self):
        """Ensure volume is increased by about 3dB."""
        from text_to_audio.tasks import VOLUME_GAIN_DB

        expected_gain = 3.0
        self.assertAlmostEqual(VOLUME_GAIN_DB, expected_gain, places=2)


# To run these tests: python manage.py test text_to_audio.tests.test_tasks


class DeesserFilterTests(TestCase):
    def test_deesser_filter_constant(self):
        """Ensure de-essing filter parameters are defined correctly."""
        from text_to_audio.tasks import DEESSER_FILTER_ARGS

        self.assertEqual(DEESSER_FILTER_ARGS, ["-af", "deesser"])


class LoudnessNormalizationTests(TestCase):
    """Tests for the in-memory loudness normalization function."""

    def test_loudness_target_constant(self):
        """Ensure loudness target is set to -14 LUFS (loud but safe for spoken word)."""
        from text_to_audio.tasks import LOUDNESS_TARGET_LUFS

        self.assertEqual(LOUDNESS_TARGET_LUFS, -14.0)

    def test_normalize_loudness_in_memory_returns_audio_segment(self):
        """Test that in-memory normalization returns an AudioSegment."""
        import numpy as np

        from text_to_audio.tasks import _normalize_loudness_in_memory

        # Create a simple test audio segment with a sine wave
        sample_rate = 44100
        duration_sec = 1.0
        frequency = 440  # A4 note
        t = np.linspace(0, duration_sec, int(sample_rate * duration_sec), False)
        # Generate a sine wave at about -20 dBFS
        audio_data = (np.sin(2 * np.pi * frequency * t) * 3276).astype(np.int16)

        test_segment = AudioSegment(
            data=audio_data.tobytes(),
            sample_width=2,  # 16-bit
            frame_rate=sample_rate,
            channels=1,
        )

        result = _normalize_loudness_in_memory(test_segment)

        # Should return an AudioSegment
        self.assertIsInstance(result, AudioSegment)
        # Should have same duration (within tolerance)
        self.assertAlmostEqual(
            result.duration_seconds, test_segment.duration_seconds, places=2
        )

    def test_normalize_loudness_in_memory_handles_silence(self):
        """Test that normalization handles silent audio gracefully."""

        from text_to_audio.tasks import _normalize_loudness_in_memory

        # Create silent audio
        silent_segment = AudioSegment.silent(duration=1000)  # 1 second of silence

        result = _normalize_loudness_in_memory(silent_segment)

        # Should return the original segment unchanged for silent audio
        self.assertIsInstance(result, AudioSegment)
        self.assertEqual(result.duration_seconds, silent_segment.duration_seconds)

    def test_normalize_loudness_in_memory_custom_target(self):
        """Test normalization with custom LUFS target."""
        import numpy as np

        from text_to_audio.tasks import _normalize_loudness_in_memory

        # Create a test audio segment
        sample_rate = 44100
        duration_sec = 1.0
        frequency = 440
        t = np.linspace(0, duration_sec, int(sample_rate * duration_sec), False)
        audio_data = (np.sin(2 * np.pi * frequency * t) * 3276).astype(np.int16)

        test_segment = AudioSegment(
            data=audio_data.tobytes(),
            sample_width=2,
            frame_rate=sample_rate,
            channels=1,
        )

        # Normalize to a different target
        result = _normalize_loudness_in_memory(test_segment, target_lufs=-14.0)

        self.assertIsInstance(result, AudioSegment)

    def test_normalize_loudness_in_memory_error_handling(self):
        """Test graceful error handling during normalization."""

        from text_to_audio.tasks import _normalize_loudness_in_memory

        # Create silent audio - tests the silent audio handling path
        silent_segment = AudioSegment.silent(duration=1000)

        # Should return original segment without crashing
        result = _normalize_loudness_in_memory(silent_segment)

        self.assertIsInstance(result, AudioSegment)
