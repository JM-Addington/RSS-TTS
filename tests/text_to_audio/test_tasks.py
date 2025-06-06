"""Tests for the text_to_audio app's task functions.

This module contains tests for the text chunking algorithm and article processing
functionality.
"""

# mypy: disable-error-code="attr-defined"

from __future__ import annotations

import shutil
from pathlib import Path
from unittest.mock import MagicMock, PropertyMock, patch

from django.conf import settings
from django.contrib.auth import get_user_model

# Transaction import is used by decorator
from django.test import TestCase, override_settings
from openai import APIError as OpenAIAPIError  # Renamed to avoid conflict

from text_to_audio.models import Article, Feed, OpenAIUsageStats
from text_to_audio.tasks import _clamp_tts_speed, _legacy_chunk_text, process_article

User = get_user_model()

# Use a temporary media root for tests
TEST_MEDIA_ROOT = Path(settings.BASE_DIR) / "test_media_tasks"


@override_settings(MEDIA_ROOT=TEST_MEDIA_ROOT)
class ChunkTextTests(TestCase):
    """Tests for the _legacy_chunk_text function.

    These tests verify that the text chunking algorithm properly splits text at natural
    language boundaries while respecting the maximum length constraint.
    """

    def test_empty_string(self):
        """Test that an empty string returns an empty list of chunks."""
        success, chunks = _legacy_chunk_text("")
        self.assertTrue(success)
        self.assertEqual(chunks, [])

    def test_short_string(self):
        """Test that a short string (under max length) is kept as one chunk."""
        text = "This is a short sentence."
        success, chunks = _legacy_chunk_text(text, max_length=100)
        self.assertTrue(success)
        self.assertEqual(chunks, [text])

    def test_string_equals_max_length(self):
        """Test that a string exactly equal to max length is kept as one chunk."""
        text = "abcde"
        success, chunks = _legacy_chunk_text(text, max_length=5)
        self.assertTrue(success)
        self.assertEqual(chunks, [text])

    def test_string_needs_one_split_by_space(self):
        """Test that a string is properly split at word boundaries when needed."""
        # Explicitly 40 chars with trailing spaces
        text = "This is a sentence that needs splitting.  "
        success, chunks = _legacy_chunk_text(text, max_length=20)
        self.assertTrue(success)
        # Should properly split into chunks smaller than max_length
        for chunk in chunks:
            self.assertLessEqual(len(chunk), 20)

    def test_string_needs_multiple_splits(self):
        """Test that a string requiring multiple splits is properly chunked."""
        text = "one two three four five six seven eight nine ten"
        success, chunks = _legacy_chunk_text(text, max_length=17)
        self.assertTrue(success)
        # Ensure each chunk is within limits
        for chunk in chunks:
            self.assertLessEqual(len(chunk), 17)
        # Ensure all words are preserved
        combined = " ".join(chunks)
        for word in text.split():
            self.assertIn(word, combined)

    def test_split_respects_paragraph_breaks(self):
        """Test that text is properly split at paragraph boundaries when possible."""
        text = "First paragraph.\n\nSecond paragraph, which is a bit longer."
        success, chunks_ml50 = _legacy_chunk_text(text, max_length=50)
        self.assertTrue(success)
        # Should split into 2 paragraphs
        self.assertEqual(len(chunks_ml50), 2)

        success, chunks_ml30 = _legacy_chunk_text(text, max_length=30)
        self.assertTrue(success)
        # Each chunk should be <= max_length
        for chunk in chunks_ml30:
            self.assertLessEqual(len(chunk), 30)

    def test_split_respects_sentence_breaks(self):
        """Test that text is properly split at sentence boundaries when possible."""
        text = "First sentence. Second sentence, also fairly short. Third one."
        success, chunks = _legacy_chunk_text(text, max_length=40)
        self.assertTrue(success)
        # Should split at sentence boundaries
        self.assertEqual(len(chunks), 3)
        self.assertIn("First sentence", chunks[0])
        self.assertIn("Second sentence", chunks[1])
        self.assertIn("Third one", chunks[2])

    def test_long_word_handling(self):
        """Test long words with forced splitting."""
        text = "Supercalifragilisticexpialidocious"
        success, chunks = _legacy_chunk_text(text, max_length=20)
        # This word will need to be force-split
        for chunk in chunks:
            self.assertLessEqual(len(chunk), 20)

    def test_force_split_if_no_natural_break(self):
        """Test text with no natural breaks."""
        text = "abcdefghijklmnopqrstuvwxyz"
        success, chunks = _legacy_chunk_text(text, max_length=20)
        # Should indicate compromised splitting for words
        self.assertFalse(success)
        for chunk in chunks:
            self.assertLessEqual(len(chunk), 20)

    def test_mixed_content_with_various_breaks(self):
        """Test text with mixed content types."""
        text = (
            "Short. Longer sentence here.\n\n"
            "New paragraph. Another sentence. And a final one."
        )
        success, chunks = _legacy_chunk_text(text, max_length=30)
        self.assertTrue(success)
        # Each chunk should be <= max_length
        for chunk in chunks:
            self.assertLessEqual(len(chunk), 30)
        # Should have all content preserved
        combined = " ".join(chunks)
        for word in text.replace("\n", " ").split():
            self.assertIn(word, combined)

    def test_huck_finn_excerpt(self):
        """Test chunking with a realistic text sample from Huckleberry Finn."""
        fixture_path = (
            Path(__file__).parent.parent / "fixtures" / "huckfinn_excerpt.txt"
        )
        with open(fixture_path, "r") as f:
            text = f.read()

        # Test with realistic TTS max length (4000 chars)
        success, chunks = _legacy_chunk_text(text, max_length=4000)
        self.assertTrue(success)
        self.assertTrue(len(chunks) >= 1)  # Should have at least one chunk
        for chunk in chunks:
            self.assertLessEqual(len(chunk), 4000)

        # Test with medium max_length (1000 chars) - more realistic for API calls
        success, chunks = _legacy_chunk_text(text, max_length=1000)
        self.assertTrue(success)
        self.assertTrue(len(chunks) >= 3)  # Should have several chunks
        for chunk in chunks:
            self.assertLessEqual(len(chunk), 1000)

        # Test with smaller max_length (200 chars) - should split on sentences
        success, chunks = _legacy_chunk_text(text, max_length=200)
        self.assertTrue(success)
        self.assertTrue(len(chunks) >= 10)  # Should have many chunks
        for chunk in chunks:
            self.assertLessEqual(len(chunk), 200)

        # Test with very small max_length (20 chars) - should force word splitting
        success, chunks = _legacy_chunk_text(text, max_length=20)
        # May be false if words need to be forcibly split
        self.assertTrue(len(chunks) > 0)
        for chunk in chunks:
            self.assertLessEqual(len(chunk), 20)

    def test_legacy_chunk_text_large_continuous_input_no_infinite_loop(self):
        """Test that _legacy_chunk_text doesn't get stuck in infinite loop with large continuous text."""
        # Create a 5000+ character string with no natural breaks
        # This would previously cause an infinite loop
        large_continuous_text = "a" * 5000

        # Use a small max_length to force multiple splits
        max_length = 100
        success, chunks = _legacy_chunk_text(
            large_continuous_text, max_length=max_length
        )

        # Should complete without hanging and produce chunks
        self.assertTrue(len(chunks) > 0)  # Should produce chunks

        # Each chunk should be within the max_length limit
        for chunk in chunks:
            self.assertLessEqual(len(chunk), max_length)

        # All characters should be preserved
        combined_length = sum(len(chunk) for chunk in chunks)
        self.assertEqual(combined_length, len(large_continuous_text))

        # Should produce the expected number of chunks (50 chunks of 100 chars each)
        expected_chunks = len(large_continuous_text) // max_length
        self.assertEqual(len(chunks), expected_chunks)

        # The key test: this should complete in reasonable time (not hang in infinite loop)
        # If the fix wasn't applied, this test would never complete

    def test_legacy_chunk_text_stress_test_completion(self):
        """Stress test to ensure _legacy_chunk_text completes for various edge cases."""
        # Test cases that could potentially cause infinite loops
        test_cases = [
            ("a" * 1000, 100),  # Very long continuous text
            ("word" * 300, 50),  # Repeated words
            ("x" * 500 + " end", 100),  # Long sequence with break at end
        ]

        for text, max_len in test_cases:
            with self.subTest(text_len=len(text), max_length=max_len):
                success, chunks = _legacy_chunk_text(text, max_length=max_len)

                # Key assertion: should complete without hanging
                self.assertTrue(len(chunks) > 0)

                # Each chunk should be within limits
                for chunk in chunks:
                    self.assertLessEqual(len(chunk), max_len)

                # Should preserve content length approximately (accounting for whitespace)
                total_chunk_chars = sum(len(chunk) for chunk in chunks)
                self.assertGreaterEqual(
                    total_chunk_chars, len(text) * 0.9
                )  # Allow some variance


@override_settings(MEDIA_ROOT=TEST_MEDIA_ROOT, OPENAI_API_KEY="test_api_key")
@patch("text_to_audio.tasks.openai.OpenAI")
class ProcessArticleTests(TestCase):
    """Tests for the process_article task.

    These tests verify the functionality of the article processing task, including
    text-to-speech conversion, error handling, and file management.
    """

    @staticmethod
    def create_dummy_file_side_effect(path_arg, *args, **kwargs):
        """Create a dummy file for testing purposes.

        Used as a side effect for mocked stream_to_file calls.
        Can handle additional arguments that AudioSegment.export() might pass.
        """
        Path(path_arg).parent.mkdir(parents=True, exist_ok=True)
        with open(path_arg, "wb") as f:
            # Slightly more unique content
            f.write(b"dummy audio data for testing purposes")
        return None

    def setUp(self):
        """Set up test data and environment for each test.

        Creates test directories, user, feed, article and mocks.
        """
        if TEST_MEDIA_ROOT.exists():
            shutil.rmtree(TEST_MEDIA_ROOT)
        TEST_MEDIA_ROOT.mkdir(parents=True, exist_ok=True)

        self.user = User.objects.create_user(
            username="testuser", password="password"
        )  # type: ignore[attr-defined]
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
        # This will be the default retry mock, can be overridden per test
        self.mock_task_instance.retry = MagicMock(
            side_effect=Exception("Celery general retry called")
        )

    def tearDown(self):
        """Clean up test data and environment after each test.

        Removes test directories created during tests.
        """
        if TEST_MEDIA_ROOT.exists():
            shutil.rmtree(TEST_MEDIA_ROOT)

    @patch("text_to_audio.tasks.AudioSegment.from_mp3")
    @patch("text_to_audio.tasks.AudioSegment.empty")
    def test_process_article_success_single_chunk(
        self, mock_audio_empty, mock_audio_from_mp3, MockOpenAIClient
    ):
        """Test that processing an article with a single text chunk works correctly."""
        mock_openai_instance = MockOpenAIClient.return_value
        mock_speech_create = mock_openai_instance.audio.speech.create

        mock_tts_response = MagicMock()
        # Simulate token usage from OpenAI client response
        mock_tts_response.usage = MagicMock(total_tokens=123)
        mock_tts_response.stream_to_file.side_effect = (
            self.create_dummy_file_side_effect
        )
        mock_speech_create.return_value = mock_tts_response

        mock_audio_segment = MagicMock()
        mock_audio_segment.set_frame_rate.return_value = mock_audio_segment
        # Use a proper side effect function for export that creates the file

        def export_side_effect(*args, **kwargs):
            # Handle the different ways pydub.export might be called
            if args:
                path_arg = args[0]  # First positional argument
            else:
                path_arg = kwargs.get("out_f")  # Keyword argument

            if path_arg:
                self.create_dummy_file_side_effect(path_arg)
            return None

        mock_audio_segment.export.side_effect = export_side_effect
        mock_audio_from_mp3.return_value = mock_audio_segment
        mock_audio_empty.return_value = MagicMock()

        result = process_article(self.article.id)

        self.article.refresh_from_db()
        self.assertEqual(result, f"Article {self.article.id} processed successfully.")
        self.assertEqual(self.article.status, Article.COMPLETED)
        self.assertIsNotNone(self.article.audio_file_path)
        self.assertTrue(
            (TEST_MEDIA_ROOT / self.article.audio_file_path).exists(),
            f"File not found: {TEST_MEDIA_ROOT / self.article.audio_file_path}",
        )
        self.assertIsNone(self.article.error_message)

        # Verify the mock calls specific to the new export parameters
        mock_audio_segment.set_frame_rate.assert_called_once_with(44100)
        mock_audio_segment.export.assert_called_once()
        # Verify export parameters (CBR and tags)
        export_call = mock_audio_segment.export.call_args
        self.assertEqual(export_call[1]["bitrate"], "128k")
        self.assertEqual(export_call[1]["format"], "mp3")
        self.assertIn("tags", export_call[1])
        self.assertIn("parameters", export_call[1])

        # Check that tags are set
        tags = export_call[1]["tags"]
        self.assertEqual(tags["title"], "Test Article")
        self.assertEqual(tags["artist"], "Test Feed")
        self.assertEqual(tags["album"], "Test Feed")

        # Check for ID3v2.3 parameters
        parameters = export_call[1]["parameters"]
        self.assertIn("-id3v2_version", parameters)
        self.assertIn("3", parameters)

        # Verify other basic mock calls
        mock_speech_create.assert_called_once()
        mock_tts_response.stream_to_file.assert_called_once()

        # Verify OpenAIUsageStats creation
        self.assertEqual(OpenAIUsageStats.objects.count(), 1)
        stats_obj = OpenAIUsageStats.objects.first()
        if stats_obj:  # Add type narrowing check for mypy
            self.assertEqual(stats_obj.user, self.article.feed.user)
            self.assertEqual(stats_obj.article, self.article)
            # From mock_tts_response.usage.total_tokens
            self.assertEqual(stats_obj.tokens_used, 123)
            self.assertTrue(stats_obj.processing_time_ms >= 0)
            # Check word count (sample text has 13 words with title)
            self.assertEqual(stats_obj.word_count, 13)

        # Verify instructions parameter is passed
        call_args = mock_speech_create.call_args[1]
        self.assertIn("instructions", call_args)
        self.assertIsInstance(call_args["instructions"], str)
        self.assertTrue(len(call_args["instructions"]) > 0)

    @patch("text_to_audio.tasks.AudioSegment.from_mp3")
    @patch("text_to_audio.tasks.AudioSegment.empty")
    @patch("text_to_audio.tasks._generate_title")
    def test_process_article_generates_title_when_missing(
        self,
        mock_generate_title,
        mock_audio_empty,
        mock_audio_from_mp3,
        MockOpenAIClient,
    ):
        """Article without a title should get one during processing."""
        self.article.title = ""
        self.article.save()

        mock_generate_title.return_value = "Auto"

        mock_openai_instance = MockOpenAIClient.return_value
        mock_speech_create = mock_openai_instance.audio.speech.create

        mock_tts_response = MagicMock()
        mock_tts_response.usage = MagicMock(total_tokens=10)
        mock_tts_response.stream_to_file.side_effect = (
            self.create_dummy_file_side_effect
        )
        mock_speech_create.return_value = mock_tts_response

        mock_audio_segment = MagicMock()
        mock_audio_segment.set_frame_rate.return_value = mock_audio_segment

        def export_side_effect(*args, **kwargs):
            path_arg = args[0] if args else kwargs.get("out_f")
            if path_arg:
                self.create_dummy_file_side_effect(path_arg)
            return None

        mock_audio_segment.export.side_effect = export_side_effect
        mock_audio_from_mp3.return_value = mock_audio_segment
        mock_audio_empty.return_value = MagicMock()

        result = process_article(self.article.id)

        self.article.refresh_from_db()
        self.assertEqual(result, f"Article {self.article.id} processed successfully.")
        self.assertEqual(self.article.title, "Auto")
        mock_generate_title.assert_called_once()

    def test_process_article_success_multiple_chunks(self, MockOpenAIClient):
        """Test processing an article with multiple text chunks."""
        # Test that our path works for combining multiple audio files
        # Use a simpler approach that doesn't rely on complicated mocking behavior

        # Use a simplified text content
        self.article.text_content = "Test content for multiple chunks"
        self.article.save()

        # Ensure the media directory exists
        article_media_dir = (
            TEST_MEDIA_ROOT
            / "articles"
            / str(self.article.feed.user_id)  # type: ignore[attr-defined]
            / str(self.article.feed.id)  # type: ignore[attr-defined]
        )
        article_media_dir.mkdir(parents=True, exist_ok=True)
        final_audio_path = article_media_dir / f"article_{self.article.id}.mp3"

        # Create a dummy file that will be used as final output
        with open(final_audio_path, "wb") as f:
            f.write(b"dummy audio data for testing purposes")

        # Configure OpenAI mock to return responses
        mock_openai_instance = MockOpenAIClient.return_value
        mock_speech_create = mock_openai_instance.audio.speech.create

        mock_tts_response = MagicMock()
        # Simulate token usage for each chunk
        # Assume 50 tokens per chunk for simplicity
        mock_tts_response.usage = MagicMock(total_tokens=50)
        mock_tts_response.stream_to_file.side_effect = (
            self.create_dummy_file_side_effect
        )
        mock_speech_create.return_value = mock_tts_response

        chunks_data = ["Chunk 1 content.", "Second chunk here."]  # 3 words, 3 words

        # Create a patch to force return of multiple chunks and to mock audio processing
        with patch(
            "text_to_audio.tasks._legacy_chunk_text"
        ) as mock_legacy_chunk_text, patch(
            "text_to_audio.tasks.AudioSegment"
        ), patch.object(
            Path, "rename"
        ):  # Prevent file rename attempts

            # Return 2 chunks to force multi-chunk processing
            mock_legacy_chunk_text.return_value = (True, chunks_data)

            # Run the function
            result = process_article(self.article.id)

            # Verify the article was updated correctly
            self.article.refresh_from_db()
            self.assertEqual(self.article.status, Article.COMPLETED)
            self.assertIsNotNone(self.article.audio_file_path)

            # Verify the correct number of API calls were made
            self.assertEqual(mock_speech_create.call_count, len(chunks_data))
            self.assertEqual(
                mock_tts_response.stream_to_file.call_count, len(chunks_data)
            )

            # Verify OpenAIUsageStats creation
            self.assertEqual(OpenAIUsageStats.objects.count(), len(chunks_data))
            stats_records = OpenAIUsageStats.objects.order_by("id")
            for i, stat_record in enumerate(stats_records):
                self.assertEqual(stat_record.user, self.article.feed.user)
                self.assertEqual(stat_record.article, self.article)
                self.assertEqual(stat_record.tokens_used, 50)  # From mock
                self.assertTrue(stat_record.processing_time_ms >= 0)
                self.assertEqual(stat_record.word_count, len(chunks_data[i].split()))

            # Verify the success message
            self.assertEqual(
                result, f"Article {self.article.id} processed successfully."
            )

    @patch("text_to_audio.tasks.AudioSegment.from_mp3")
    @patch("text_to_audio.tasks.AudioSegment.empty")
    def test_process_article_stat_saving_error(
        self, mock_audio_empty, mock_audio_from_mp3, MockOpenAIClient
    ):
        """Test that process_article handles usage stats saving errors."""
        # We need to create a custom failing OpenAIUsageStats.objects.create
        from unittest.mock import patch

        # Define a custom side effect that raises an exception
        def raise_db_error(*args, **kwargs):
            raise Exception("DB error saving stats")

        # Configure the mock response
        mock_openai_instance = MockOpenAIClient.return_value
        mock_speech_create = mock_openai_instance.audio.speech.create

        # Create a properly mocked response
        mock_tts_response = MagicMock(spec=["stream_to_file"])
        # Create a usage attribute with total_tokens that can be converted to int
        usage_mock = MagicMock()
        usage_mock.total_tokens = 100
        type(mock_tts_response).usage = PropertyMock(return_value=usage_mock)

        mock_tts_response.stream_to_file.side_effect = (
            self.create_dummy_file_side_effect
        )
        mock_speech_create.return_value = mock_tts_response

        mock_audio_segment = MagicMock()
        mock_audio_segment.set_frame_rate.return_value = mock_audio_segment

        def export_side_effect(*args, **kwargs):
            path_arg = args[0] if args else kwargs.get("out_f")
            if path_arg:
                self.create_dummy_file_side_effect(path_arg)
            return None

        mock_audio_segment.export.side_effect = export_side_effect
        mock_audio_from_mp3.return_value = mock_audio_segment
        mock_audio_empty.return_value = MagicMock()

        # Skip actual retry attempt
        with patch("text_to_audio.tasks.process_article.retry") as mock_retry:
            # Make retry return None instead of raising
            mock_retry.return_value = None

            # Make OpenAIUsageStats.objects.create raise an error
            with patch(
                "text_to_audio.models.OpenAIUsageStats.objects.create",
                side_effect=raise_db_error,
            ):
                with self.assertLogs(
                    "text_to_audio.tasks", level="ERROR"
                ) as log_watcher:
                    result = process_article(self.article.id)

        self.article.refresh_from_db()
        self.assertEqual(result, f"Article {self.article.id} processed successfully.")
        self.assertEqual(self.article.status, Article.COMPLETED)  # Main task completes
        self.assertIsNotNone(self.article.audio_file_path)
        self.assertEqual(OpenAIUsageStats.objects.count(), 0)  # Stats saving failed

        self.assertTrue(
            any(
                "Failed to save OpenAIUsageStats" in message
                for message in log_watcher.output
            ),
            "Log does not contain expected OpenAIUsageStats failure message",
        )
        # Check that the error was logged (the exact message may vary)
        # The ChunkTone service creates fallback chunks with index chunk_tone_0
        self.assertTrue(
            any(
                "Failed to save OpenAIUsageStats for article 1, chunk chunk_tone_0:"
                in message
                for message in log_watcher.output
            ),
            f"Log does not contain detailed stats saving error message. Actual logs: {log_watcher.output}",
        )

    @patch("text_to_audio.tasks.AudioSegment.from_mp3")
    @patch("text_to_audio.tasks.AudioSegment.empty")
    @patch("text_to_audio.tasks._save_openai_usage_stats")  # Patch the helper function
    def test_process_article_token_extraction_from_headers(
        self, mock_save_stats, mock_audio_empty, mock_audio_from_mp3, MockOpenAIClient
    ):
        """Test token extraction from response headers."""
        # Configure the mock response properly
        mock_openai_instance = MockOpenAIClient.return_value
        mock_speech_create = mock_openai_instance.audio.speech.create

        # Create a response with headers but no usage attribute
        mock_tts_response = MagicMock(spec=["headers", "stream_to_file"])
        mock_tts_response.headers = {"x-openai-tokens-used": "150"}
        # Ensure hasattr(response, "usage") returns False
        type(mock_tts_response).usage = PropertyMock(side_effect=AttributeError)

        mock_tts_response.stream_to_file.side_effect = (
            self.create_dummy_file_side_effect
        )
        mock_speech_create.return_value = mock_tts_response

        mock_audio_segment = MagicMock()
        mock_audio_segment.set_frame_rate.return_value = mock_audio_segment

        def export_side_effect(*args, **kwargs):
            path_arg = args[0] if args else kwargs.get("out_f")
            if path_arg:
                self.create_dummy_file_side_effect(path_arg)
            return None

        mock_audio_segment.export.side_effect = export_side_effect
        mock_audio_from_mp3.return_value = mock_audio_segment
        mock_audio_empty.return_value = MagicMock()

        # Process the article
        process_article(self.article.id)

        # Verify the helper function was called with expected args
        mock_save_stats.assert_called_once()
        call_args = mock_save_stats.call_args[1]
        self.assertEqual(call_args["tokens_used"], 150)
        self.assertEqual(call_args["user"], self.article.feed.user)
        self.assertEqual(call_args["article"], self.article)

    @patch("text_to_audio.tasks.AudioSegment.from_mp3")
    @patch("text_to_audio.tasks.AudioSegment.empty")
    @patch("text_to_audio.tasks._save_openai_usage_stats")  # Patch the helper function
    def test_process_article_token_extraction_fallback(
        self, mock_save_stats, mock_audio_empty, mock_audio_from_mp3, MockOpenAIClient
    ):
        """Test token extraction fallback to 0 when no token info is present."""
        mock_openai_instance = MockOpenAIClient.return_value
        mock_speech_create = mock_openai_instance.audio.speech.create

        # Create a response with no usage and irrelevant headers
        mock_tts_response = MagicMock(spec=["headers", "stream_to_file"])
        mock_tts_response.headers = {"some-other-header": "some-value"}
        # Ensure hasattr(response, "usage") returns False
        type(mock_tts_response).usage = PropertyMock(side_effect=AttributeError)

        mock_tts_response.stream_to_file.side_effect = (
            self.create_dummy_file_side_effect
        )
        mock_speech_create.return_value = mock_tts_response

        mock_audio_segment = MagicMock()
        mock_audio_segment.set_frame_rate.return_value = mock_audio_segment

        def export_side_effect(*args, **kwargs):
            path_arg = args[0] if args else kwargs.get("out_f")
            if path_arg:
                self.create_dummy_file_side_effect(path_arg)
            return None

        mock_audio_segment.export.side_effect = export_side_effect
        mock_audio_from_mp3.return_value = mock_audio_segment
        mock_audio_empty.return_value = MagicMock()

        # Process the article - don't check logs in this test
        process_article(self.article.id)

        # Verify the helper function was called with expected args
        mock_save_stats.assert_called_once()
        call_args = mock_save_stats.call_args[1]
        self.assertEqual(call_args["tokens_used"], 0)  # Fallback value
        self.assertEqual(call_args["user"], self.article.feed.user)
        self.assertEqual(call_args["article"], self.article)

    def test_process_article_openai_api_error_with_retry(self, MockOpenAIClient):
        """Test handling of OpenAI API errors with proper retry logic."""
        mock_openai_instance = MockOpenAIClient.return_value
        mock_speech_create = mock_openai_instance.audio.speech.create
        mock_speech_create.side_effect = OpenAIAPIError(
            "TTS failed", request=MagicMock(), body=None
        )

        # Mock the Celery retry functionality
        with patch(
            "text_to_audio.tasks.process_article.retry",
            side_effect=Exception("Celery OpenAI error retry"),
        ) as mock_retry:
            with self.assertRaises(Exception) as cm:
                process_article(self.article.id)
            self.assertEqual(str(cm.exception), "Celery OpenAI error retry")

            self.article.refresh_from_db()
            self.assertEqual(self.article.status, Article.FAILED)
            self.assertIsNotNone(self.article.error_message)
            self.assertIn("APIError: TTS failed", self.article.error_message)
            mock_retry.assert_called_once()

    @patch("django.db.transaction.atomic", lambda inner_func=None: inner_func)
    def test_process_article_pydub_error(self, MockOpenAIClient):
        """Test handling of pydub errors during audio processing."""
        # Need to create multiple chunks to force the pydub error path
        self.article.text_content = (
            "Test content for multiple chunks to ensure stitching. " * 10
        )
        self.article.save()

        mock_openai_instance = MockOpenAIClient.return_value
        mock_speech_create = mock_openai_instance.audio.speech.create

        mock_tts_response = MagicMock()
        mock_tts_response.stream_to_file.side_effect = (
            self.create_dummy_file_side_effect
        )
        mock_speech_create.return_value = mock_tts_response

        # Skip stats creation to avoid transaction issues
        with patch("text_to_audio.tasks._save_openai_usage_stats"):
            # Need to mock AudioSegment.empty() and patch retry
            with patch("text_to_audio.tasks.AudioSegment.empty") as mock_audio_empty:
                # Configure AudioSegment to work properly until we hit the combine phase
                mock_combined_audio = MagicMock()
                mock_audio_empty.return_value = mock_combined_audio

                # Simulate a pydub error during combination
                with patch(
                    "text_to_audio.tasks.AudioSegment.from_mp3",
                    side_effect=Exception("Pydub test error"),
                ), patch(
                    "text_to_audio.tasks.process_article.retry",
                    side_effect=Exception("Celery Pydub error retry"),
                ) as mock_retry:

                    with self.assertRaises(Exception) as cm:
                        process_article(self.article.id)
                    self.assertEqual(str(cm.exception), "Celery Pydub error retry")

                    self.article.refresh_from_db()
                    self.assertEqual(self.article.status, Article.FAILED)
                    self.assertIsNotNone(self.article.error_message)
                    self.assertIn("Pydub test error", self.article.error_message)
                    mock_retry.assert_called_once()

    def test_process_article_empty_text_content(self, MockOpenAIClient):
        """Test handling of articles with empty text content."""
        self.article.text_content = ""
        self.article.save()

        # Mock the Celery retry functionality
        with patch(
            "text_to_audio.tasks.process_article.retry",
            side_effect=Exception("Celery empty content retry"),
        ) as mock_retry:
            with self.assertRaises(Exception) as cm:
                process_article(self.article.id)
            self.assertEqual(str(cm.exception), "Celery empty content retry")

            self.article.refresh_from_db()
            self.assertEqual(self.article.status, Article.FAILED)
            self.assertIsNotNone(self.article.error_message)
            self.assertIn("Article text_content is empty.", self.article.error_message)
            mock_retry.assert_called_once()

    def test_article_not_found(self, MockOpenAIClient):
        """Test handling of non-existent article IDs."""
        result = process_article.apply(
            args=[99999], instance=self.mock_task_instance
        ).get()
        self.assertEqual(result, "Article 99999 not found.")

    # Patch the helper function to avoid DB issues
    @patch("text_to_audio.tasks._save_openai_usage_stats")
    def test_temp_files_cleaned_up_on_success(self, mock_save_stats, MockOpenAIClient):
        """Test temporary files cleanup after successful processing."""
        mock_openai_instance = MockOpenAIClient.return_value
        mock_speech_create = mock_openai_instance.audio.speech.create

        # Create a properly mocked response
        mock_tts_response = MagicMock(spec=["stream_to_file"])
        # Create a usage attribute with total_tokens that can be converted to int
        usage_mock = MagicMock()
        usage_mock.total_tokens = 100
        type(mock_tts_response).usage = PropertyMock(return_value=usage_mock)

        mock_tts_response.stream_to_file.side_effect = (
            self.create_dummy_file_side_effect
        )
        mock_speech_create.return_value = mock_tts_response

        # Use a text that will produce exactly 2 chunks for consistent testing
        # Override _legacy_chunk_text to return exactly 2 chunks
        chunks = ["Chunk one for cleanup.", "Chunk two for cleanup."]

        with patch(
            "text_to_audio.tasks._legacy_chunk_text", return_value=(True, chunks)
        ):
            # Patch django transaction.atomic to avoid transaction issues in tests
            with patch("django.db.transaction.atomic", lambda func=None: func):
                with patch("text_to_audio.tasks.os.remove") as mock_os_remove:
                    mock_combined_audio = MagicMock()
                    mock_combined_audio.export.side_effect = (
                        self.create_dummy_file_side_effect
                    )

                    mock_audio_segment = MagicMock()  # Mock for the segments themselves

                    with patch(
                        "text_to_audio.tasks.AudioSegment.empty",
                        return_value=mock_combined_audio,
                    ), patch(
                        "text_to_audio.tasks.AudioSegment.from_mp3",
                        return_value=mock_audio_segment,
                    ):
                        process_article(self.article.id)

                    self.article.refresh_from_db()
                    self.assertEqual(self.article.status, Article.COMPLETED)
                    # Verify cleanup was called
                    mock_os_remove.assert_called()

    @patch("django.db.transaction.atomic", lambda inner_func=None: inner_func)
    def test_temp_files_cleaned_up_on_failure(self, MockOpenAIClient):
        """Test temporary files cleanup when processing fails."""
        # Use a smaller text content to make the test faster
        self.article.text_content = "First chunk content. " * 5
        self.article.save()

        mock_openai_instance = MockOpenAIClient.return_value
        mock_speech_create = mock_openai_instance.audio.speech.create

        # Create a response for the first chunk that will succeed
        mock_successful_tts_response = MagicMock()
        mock_successful_tts_response.stream_to_file.side_effect = (
            self.create_dummy_file_side_effect
        )

        # Configure the mock to succeed for first chunk and fail for second
        mock_speech_create.side_effect = [
            mock_successful_tts_response,
            OpenAIAPIError(
                "TTS failed on second chunk", request=MagicMock(), body=None
            ),
        ]

        # Skip stats creation to avoid transaction issues
        with patch("text_to_audio.tasks._save_openai_usage_stats"), patch(
            "text_to_audio.tasks.ContentAnalysisService"
        ) as MockContentAnalysisService:

            # Mock content analysis to return None, forcing single voice path initially
            mock_analysis_instance = MockContentAnalysisService.return_value
            mock_analysis_instance.analyze_content.return_value = None

            # Mock os.remove to verify calls and patch _legacy_chunk_text for 2 chunks
            with patch("text_to_audio.tasks.os.remove") as mock_os_remove, patch(
                "text_to_audio.tasks._legacy_chunk_text"
            ) as mock_legacy_chunk_text, patch(
                "text_to_audio.tasks.process_article.retry",
                side_effect=Exception("Celery failure cleanup retry"),
            ):

                # Force the function to process 2 chunks
                mock_legacy_chunk_text.return_value = (True, ["Chunk 1", "Chunk 2"])

                # The test should raise an exception when retry is called
                with self.assertRaises(Exception) as cm:
                    process_article(self.article.id)
                self.assertEqual(str(cm.exception), "Celery failure cleanup retry")

                # Verify the mock was called correctly
                mock_successful_tts_response.stream_to_file.assert_called_once()

                # Check that at least one temp file was cleaned up
                self.assertTrue(
                    mock_os_remove.call_count >= 1,
                    (
                        f"Expected os.remove to be called at least once, "
                        f"got {mock_os_remove.call_count} calls"
                    ),
                )

    @patch("text_to_audio.tasks.ContentAnalysisService")
    @patch("text_to_audio.tasks.AudioSegment.from_mp3")
    @patch("text_to_audio.tasks.AudioSegment.empty")
    def test_process_article_successful_multi_voice(
        self,
        mock_audio_empty,
        mock_audio_from_mp3,
        MockContentAnalysisService,
        MockOpenAIClient,
    ):
        """Test successful multi-voice processing."""
        mock_openai_instance = MockOpenAIClient.return_value
        mock_speech_create = mock_openai_instance.audio.speech.create
        mock_tts_response = MagicMock()
        mock_tts_response.stream_to_file.side_effect = (
            self.create_dummy_file_side_effect
        )
        mock_speech_create.return_value = mock_tts_response

        mock_audio_segment = MagicMock()
        mock_audio_segment.set_frame_rate.return_value = mock_audio_segment
        mock_audio_segment.export.side_effect = (
            self.create_dummy_file_side_effect
        )  # Simulate file creation
        mock_audio_from_mp3.return_value = mock_audio_segment
        mock_audio_empty.return_value = MagicMock()  # For combining segments

        valid_multi_voice_data = {
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

        # Mock ContentAnalysisService to set multi_voice_data
        # Or, ensure _is_valid_multi_voice_data will use this if we set it directly
        self.article.multi_voice_data = valid_multi_voice_data
        self.article.save()

        # Mock _is_valid_multi_voice_data to return True
        # to ensure multi-voice path is taken
        with patch(
            "text_to_audio.tasks._is_valid_multi_voice_data", return_value=True
        ), patch("text_to_audio.tasks._save_openai_usage_stats") as mock_save_stats:
            result = process_article(self.article.id)

        self.article.refresh_from_db()
        self.assertEqual(result, f"Article {self.article.id} processed successfully.")
        self.assertEqual(self.article.status, Article.COMPLETED)
        self.assertIsNotNone(self.article.audio_file_path)

        self.assertEqual(mock_speech_create.call_count, 2)
        calls = mock_speech_create.call_args_list
        # First call for narrator
        self.assertEqual(calls[0][1]["input"], "Chapter one.")
        self.assertEqual(calls[0][1]["voice"], "alloy")  # tts_model from "narrator"
        self.assertEqual(calls[0][1]["speed"], 1.0)
        # Second call for hero
        self.assertEqual(calls[1][1]["input"], "I am the hero!")
        self.assertEqual(calls[1][1]["voice"], "onyx")  # tts_model from "hero"
        self.assertEqual(calls[1][1]["speed"], 1.1)

        # Verify instructions parameter is passed to both calls
        self.assertIn("instructions", calls[0][1])
        self.assertIn("instructions", calls[1][1])
        self.assertIsInstance(calls[0][1]["instructions"], str)
        self.assertIsInstance(calls[1][1]["instructions"], str)
        self.assertIn(
            "neutral", calls[0][1]["instructions"]
        )  # tone from voice definition
        self.assertIn("bold", calls[1][1]["instructions"])  # tone from voice definition

        mock_audio_segment.export.assert_called_once()  # Assuming combined export
        self.assertEqual(mock_save_stats.call_count, 2)

    @patch("text_to_audio.tasks.ContentAnalysisService")
    @patch("text_to_audio.tasks.AudioSegment.from_mp3")
    @patch("text_to_audio.tasks.AudioSegment.empty")
    def test_process_article_fallback_to_single_voice(
        self,
        mock_audio_empty,
        mock_audio_from_mp3,
        MockContentAnalysisService,
        MockOpenAIClient,
    ):
        """Test fallback to single-voice processing when multi_voice_data is invalid."""
        mock_openai_instance = MockOpenAIClient.return_value
        mock_speech_create = mock_openai_instance.audio.speech.create
        mock_tts_response = MagicMock()
        mock_tts_response.stream_to_file.side_effect = (
            self.create_dummy_file_side_effect
        )
        mock_speech_create.return_value = mock_tts_response

        mock_audio_segment = MagicMock()
        mock_audio_segment.set_frame_rate.return_value = mock_audio_segment
        mock_audio_segment.duration_seconds = 1
        mock_audio_segment.export.side_effect = self.create_dummy_file_side_effect
        mock_audio_from_mp3.return_value = mock_audio_segment
        mock_audio_empty.return_value = MagicMock()

        # Set invalid multi_voice_data
        self.article.multi_voice_data = {"error": "this is not valid"}
        self.article.text_content = "This is fallback content. It is short."  # 7 words
        # Set article level voice_id and speed for fallback
        self.article.voice_id = "echo"  # Fallback voice
        self.article.speed = 0.9  # Fallback speed
        self.article.save()

        # Mock _is_valid_multi_voice_data to return False to ensure fallback path
        with patch(
            "text_to_audio.tasks._is_valid_multi_voice_data", return_value=False
        ), patch("text_to_audio.tasks._save_openai_usage_stats") as mock_save_stats:
            result = process_article(self.article.id)

        self.article.refresh_from_db()
        self.assertEqual(result, f"Article {self.article.id} processed successfully.")
        self.assertEqual(self.article.status, Article.COMPLETED)

        # _legacy_chunk_text on "Test Article.\n\nThis is fallback content. It is short."
        # is likely 1 chunk.
        expected_chunks = 1
        self.assertEqual(mock_speech_create.call_count, expected_chunks)

        # Verify fallback voice and speed were used
        call_args = mock_speech_create.call_args_list[0][1]
        self.assertEqual(call_args["voice"], "echo")
        self.assertEqual(call_args["speed"], 0.9)

        # Verify instructions parameter is passed in fallback
        self.assertIn("instructions", call_args)
        self.assertIsInstance(call_args["instructions"], str)
        # Should contain fallback voice prompt if voice_parameters exist, otherwise basic prompt

        self.assertEqual(mock_save_stats.call_count, expected_chunks)

    @patch("text_to_audio.tasks.ContentAnalysisService")
    @patch("text_to_audio.tasks.AudioSegment.from_mp3")
    @patch("text_to_audio.tasks.AudioSegment.empty")
    def test_process_article_multi_voice_segment_chunking(
        self,
        mock_audio_empty,
        mock_audio_from_mp3,
        MockContentAnalysisService,
        MockOpenAIClient,
    ):
        """Test that a long segment in multi-voice data is correctly chunked."""
        mock_openai_instance = MockOpenAIClient.return_value
        mock_speech_create = mock_openai_instance.audio.speech.create
        mock_tts_response = MagicMock()
        mock_tts_response.stream_to_file.side_effect = (
            self.create_dummy_file_side_effect
        )
        mock_speech_create.return_value = mock_tts_response

        mock_audio_segment = MagicMock()
        mock_audio_segment.set_frame_rate.return_value = mock_audio_segment
        mock_audio_segment.duration_seconds = 1
        mock_audio_segment.export.side_effect = self.create_dummy_file_side_effect
        mock_audio_from_mp3.return_value = mock_audio_segment

        combined_audio_mock = MagicMock()
        type(combined_audio_mock).duration_seconds = PropertyMock(return_value=1)
        combined_audio_mock.__iadd__.return_value = combined_audio_mock
        combined_audio_mock.set_frame_rate.return_value = combined_audio_mock
        combined_audio_mock.export.return_value = None
        mock_audio_empty.return_value = combined_audio_mock
        long_segment_text = (
            "This is a very long segment. " * 300
        )  # Approx 7*300 = 2100 chars
        short_segment_text = "This is short."

        multi_voice_data_with_long_segment = {
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
                {"text": long_segment_text, "voice_name": "long_talker"},
                {"text": short_segment_text, "voice_name": "short_talker"},
            ],
        }
        self.article.multi_voice_data = multi_voice_data_with_long_segment
        self.article.text_content = (
            long_segment_text + short_segment_text
        )  # For analysis sample if it ran
        self.article.save()

        # Determine how many chunks _legacy_chunk_text will make for long_segment_text.
        # Default max_length is 4000 and our long_segment_text is ~2100.
        # It should be 1 chunk based on length. Make it longer to force chunking.
        # Assume max_length is small for testing chunking within a segment.
        # The _legacy_chunk_text in tasks.py has max_length=4000, so make
        # long_segment_text > 4000 to test chunking.
        long_segment_text_actually_long = (
            "This is an extremely long segment designed to test chunking. " * 250
        )  # > 4000 chars

        multi_voice_data_with_long_segment["audio_segments"][0][  # type: ignore[index]
            "text"
        ] = long_segment_text_actually_long
        self.article.multi_voice_data = multi_voice_data_with_long_segment
        self.article.save()

        # Let's spy on _legacy_chunk_text to verify its calls
        with patch(
            "text_to_audio.tasks._is_valid_multi_voice_data", return_value=True
        ), patch("text_to_audio.tasks._legacy_chunk_text"), patch(
            "text_to_audio.tasks._save_openai_usage_stats"
        ) as mock_save_stats:

            # Make _legacy_chunk_text behave normally for the first call (long segment)
            # and return 1 chunk for the second call (short segment)
            # The first segment (long_segment_text_actually_long) will be
            # chunked by the actual _legacy_chunk_text.
            # The second segment (short_segment_text) will also be chunked
            # by the actual _legacy_chunk_text.

            # To properly test this, we need to let the actual _legacy_chunk_text run.
            # We are interested in the calls to speech.create.
            # If long_segment_text_actually_long results in N chunks and
            # short_segment_text in 1 chunk, then speech.create should be called
            # N+1 times.

            # Let's calculate expected chunks for long_segment_text_actually_long
            # default max_length is 4000.
            # len("This is an extremely long segment designed to test chunking.") is 62
            # 62 * 250 = 15500 characters.
            # Expected N = ceil(15500 / 4000) = ceil(3.875) = 4 chunks.
            # Short segment "This is short." is 1 chunk. Total = 5 calls to
            # speech.create.

            # We can't easily mock _legacy_chunk_text differently for different calls
            # within the loop so we'll rely on the actual _legacy_chunk_text behavior.

            process_article(self.article.id)

        self.article.refresh_from_db()
        self.assertEqual(self.article.status, Article.COMPLETED)

        # Expected calls: 4 for the long segment + 1 for the short segment
        self.assertEqual(mock_speech_create.call_count, 5)

        calls = mock_speech_create.call_args_list
        # First 4 calls should be for "long_talker"
        for i in range(4):
            # tts_model from "long_talker"
            self.assertEqual(calls[i][1]["voice"], "fable")
            self.assertEqual(calls[i][1]["speed"], 1.0)
            self.assertTrue(len(calls[i][1]["input"]) <= 4000)  # Check chunk length

        # Last call should be for "short_talker"
        # tts_model from "short_talker"
        self.assertEqual(calls[4][1]["voice"], "shimmer")
        self.assertEqual(calls[4][1]["speed"], 0.8)
        self.assertEqual(calls[4][1]["input"], short_segment_text)

        # Verify instructions parameter is passed to all calls
        for i, call in enumerate(calls):
            self.assertIn("instructions", call[1])
            self.assertIsInstance(call[1]["instructions"], str)
            if i < 4:  # First 4 calls for long_talker
                self.assertIn("verbose", call[1]["instructions"])
            else:  # Last call for short_talker
                self.assertIn("concise", call[1]["instructions"])

        self.assertEqual(mock_save_stats.call_count, 5)

    @patch("text_to_audio.tasks.ContentAnalysisService")
    @patch("text_to_audio.tasks.AudioSegment.from_mp3")
    @patch("text_to_audio.tasks.AudioSegment.empty")
    def test_process_article_long_text_full_analysis(
        self,
        mock_audio_empty,
        mock_audio_from_mp3,
        MockContentAnalysisService,
        MockOpenAIClient,
    ):
        """Ensure full article text is passed to content analysis."""
        long_text = "longword " * 1000
        self.article.text_content = long_text
        self.article.save()

        mock_analysis_instance = MockContentAnalysisService.return_value
        mock_analysis_instance.analyze_content.return_value = {
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

        mock_openai_instance = MockOpenAIClient.return_value
        mock_speech_create = mock_openai_instance.audio.speech.create
        mock_tts_response = MagicMock()
        mock_tts_response.stream_to_file.side_effect = (
            self.create_dummy_file_side_effect
        )
        mock_speech_create.return_value = mock_tts_response

        mock_audio_segment = MagicMock()
        mock_audio_segment.set_frame_rate.return_value = mock_audio_segment
        mock_audio_segment.duration_seconds = 1
        mock_audio_segment.export.side_effect = self.create_dummy_file_side_effect
        mock_audio_from_mp3.return_value = mock_audio_segment

        class DummyAudio:
            def __init__(self):
                self.duration_seconds = 1

            def __iadd__(self, other):
                return self

            def set_frame_rate(self, rate):
                return self

            def export(self, *args, **kwargs):
                return None

        mock_audio_empty.return_value = DummyAudio()

        with patch(
            "text_to_audio.tasks._is_valid_multi_voice_data",
            return_value=True,
        ), patch("text_to_audio.tasks._save_openai_usage_stats"):
            result = process_article(self.article.id)

        self.article.refresh_from_db()
        self.assertEqual(result, f"Article {self.article.id} processed successfully.")
        mock_analysis_instance.analyze_content.assert_called_once()
        self.assertEqual(
            mock_analysis_instance.analyze_content.call_args[0][0],
            long_text.strip(),
        )

        concatenated_input = "".join(
            call.kwargs["input"] for call in mock_speech_create.call_args_list
        )
        self.assertEqual(
            concatenated_input.replace(" ", ""), long_text.replace(" ", "")
        )
        self.assertEqual(
            mock_speech_create.call_count, len(mock_speech_create.call_args_list)
        )

    @patch("text_to_audio.tasks.ContentAnalysisService")
    @patch("text_to_audio.services.voice_parameter_generation.ContentAnalysisService")
    @patch("text_to_audio.tasks.VoiceConfigurationService")
    @patch("text_to_audio.tasks.AudioSegment.from_mp3")
    @patch("text_to_audio.tasks.AudioSegment.empty")
    def test_content_analysis_called_once_for_auto_feed(
        self,
        mock_audio_empty,
        mock_audio_from_mp3,
        MockVoiceConfigurationService,
        MockVoiceParameterContentAnalysisService,
        MockTasksContentAnalysisService,
        MockOpenAIClient,
    ):
        """Test that ContentAnalysisService is called exactly once for AUTO feeds."""
        # Set up the feed as AUTO mode
        from text_to_audio.models import Feed

        self.feed.voice_mode = Feed.VOICE_MODE_AUTO
        self.feed.save()

        # Configure mocks for OpenAI
        mock_openai_instance = MockOpenAIClient.return_value
        mock_speech_create = mock_openai_instance.audio.speech.create
        mock_tts_response = MagicMock()
        mock_tts_response.stream_to_file.side_effect = (
            self.create_dummy_file_side_effect
        )
        mock_speech_create.return_value = mock_tts_response

        # Configure audio processing mocks
        mock_audio_segment = MagicMock()
        mock_audio_segment.set_frame_rate.return_value = mock_audio_segment
        mock_audio_segment.export.side_effect = self.create_dummy_file_side_effect
        mock_audio_from_mp3.return_value = mock_audio_segment
        mock_audio_empty.return_value = MagicMock()

        # Configure ContentAnalysisService mock for tasks.py
        mock_tasks_analysis_instance = MockTasksContentAnalysisService.return_value
        valid_analysis_result = {
            "voices": [
                {
                    "name": "narrator",
                    "tone": "neutral",
                    "tts_model": "alloy",
                    "tts_speed": 1.0,
                }
            ],
            "audio_segments": [
                {
                    "text": "Test content for our article. It has sentences.",
                    "voice_name": "narrator",
                }
            ],
        }
        mock_tasks_analysis_instance.analyze_content.return_value = (
            valid_analysis_result
        )

        # Configure ContentAnalysisService mock for voice parameter generation
        # This should NOT be called because we're reusing the existing analysis
        mock_voice_param_analysis_instance = (
            MockVoiceParameterContentAnalysisService.return_value
        )
        mock_voice_param_analysis_instance.analyze_content.return_value = (
            valid_analysis_result
        )

        # Mock VoiceConfigurationService to avoid database issues
        mock_voice_config_instance = MockVoiceConfigurationService.return_value
        mock_voice_config_instance.configure_article_voice.return_value = self.article

        # Mock other services to avoid interference and skip stats
        with patch("text_to_audio.tasks._save_openai_usage_stats"), patch(
            "text_to_audio.tasks._is_valid_multi_voice_data", return_value=False
        ):

            result = process_article(self.article.id)

        # Verify the article was processed successfully
        self.article.refresh_from_db()
        self.assertEqual(result, f"Article {self.article.id} processed successfully.")
        self.assertEqual(self.article.status, Article.COMPLETED)

        # Critical assertion: ContentAnalysisService should be called exactly once
        # in tasks.py (first call) and NOT called in voice_parameter_generation.py
        mock_tasks_analysis_instance.analyze_content.assert_called_once()

        # The voice parameter generation service should NOT call analyze_content
        # because it should reuse the existing multi_voice_data
        mock_voice_param_analysis_instance.analyze_content.assert_not_called()

        # Verify that multi_voice_data was set correctly
        self.assertIsNotNone(self.article.multi_voice_data)
        self.assertEqual(self.article.multi_voice_data, valid_analysis_result)

    @patch("text_to_audio.tasks.ContentAnalysisService")
    @patch("text_to_audio.tasks.AudioSegment.from_mp3")
    @patch("text_to_audio.tasks.AudioSegment.empty")
    def test_process_article_long_article_chunked_analysis(
        self,
        mock_audio_empty,
        mock_audio_from_mp3,
        MockContentAnalysisService,
        MockOpenAIClient,
    ):
        """Test that articles longer than MAX_ANALYSIS_WORDS are processed in chunks."""
        from text_to_audio.services.content_analysis import MAX_ANALYSIS_WORDS

        # Create an article with more than MAX_ANALYSIS_WORDS (8000) words
        # Use simple repeated words to make it predictable
        long_text = "word " * (MAX_ANALYSIS_WORDS + 1000)  # 9000 words total
        self.article.text_content = long_text
        self.article.save()

        # Configure OpenAI mock
        mock_openai_instance = MockOpenAIClient.return_value
        mock_speech_create = mock_openai_instance.audio.speech.create
        mock_tts_response = MagicMock()
        mock_tts_response.stream_to_file.side_effect = (
            self.create_dummy_file_side_effect
        )
        mock_speech_create.return_value = mock_tts_response

        # Configure audio processing mocks
        mock_audio_segment = MagicMock()
        mock_audio_segment.set_frame_rate.return_value = mock_audio_segment
        mock_audio_segment.export.side_effect = self.create_dummy_file_side_effect
        mock_audio_from_mp3.return_value = mock_audio_segment
        mock_audio_empty.return_value = MagicMock()

        # Mock ContentAnalysisService to return different analysis for each chunk
        mock_analysis_instance = MockContentAnalysisService.return_value

        def analysis_side_effect(text, title=None):
            # Create a simple analysis that varies by chunk content
            if "Part 1" in title:
                return {
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

        # Mock _is_valid_multi_voice_data to return True for combined result
        with patch(
            "text_to_audio.tasks._is_valid_multi_voice_data", return_value=True
        ), patch("text_to_audio.tasks._save_openai_usage_stats"):
            result = process_article(self.article.id)

        # Verify the article was processed successfully
        self.article.refresh_from_db()
        self.assertEqual(result, f"Article {self.article.id} processed successfully.")
        self.assertEqual(self.article.status, Article.COMPLETED)

        # Verify ContentAnalysisService was called twice (for two chunks)
        self.assertEqual(mock_analysis_instance.analyze_content.call_count, 2)

        # Verify that multi_voice_data contains combined results
        self.assertIsNotNone(self.article.multi_voice_data)
        self.assertIn("voices", self.article.multi_voice_data)
        self.assertIn("audio_segments", self.article.multi_voice_data)

        # Should have both voices from both chunks
        voices = self.article.multi_voice_data["voices"]
        self.assertEqual(len(voices), 2)
        voice_names = {voice["name"] for voice in voices}
        self.assertEqual(voice_names, {"narrator1", "narrator2"})

        # Should have both audio segments
        segments = self.article.multi_voice_data["audio_segments"]
        self.assertEqual(len(segments), 2)

        # Verify that the combined text length covers the full article
        combined_text = "".join(segment["text"] for segment in segments)
        # Should be approximately the same length (allowing for some whitespace differences)
        self.assertGreater(len(combined_text), len(long_text) * 0.95)

        # Verify TTS was called for both segments (may be chunked further by _legacy_chunk_text)
        self.assertGreater(mock_speech_create.call_count, 0)

    @patch("text_to_audio.tasks.AudioSegment.from_mp3")
    @patch("text_to_audio.tasks.AudioSegment.empty")
    def test_process_article_speed_clamping_single_voice(
        self, mock_audio_empty, mock_audio_from_mp3, MockOpenAIClient
    ):
        """Test that speed is clamped correctly in single-voice fallback path."""
        # Test different speed values to ensure clamping works
        test_cases = [
            (0.1, 0.25),  # Below minimum
            (0.25, 0.25),  # At minimum
            (1.0, 1.0),  # Normal speed
            (4.0, 4.0),  # At maximum
            (5.0, 4.0),  # Above maximum
        ]

        for input_speed, expected_speed in test_cases:
            with self.subTest(input_speed=input_speed, expected_speed=expected_speed):
                # Set article speed
                self.article.speed = input_speed
                self.article.save()

                # Configure mocks
                mock_openai_instance = MockOpenAIClient.return_value
                mock_speech_create = mock_openai_instance.audio.speech.create
                mock_tts_response = MagicMock()
                mock_tts_response.stream_to_file.side_effect = (
                    self.create_dummy_file_side_effect
                )
                mock_speech_create.return_value = mock_tts_response

                mock_audio_segment = MagicMock()
                mock_audio_segment.set_frame_rate.return_value = mock_audio_segment
                mock_audio_segment.export.side_effect = (
                    self.create_dummy_file_side_effect
                )
                mock_audio_from_mp3.return_value = mock_audio_segment
                mock_audio_empty.return_value = MagicMock()

                # Process article
                with patch("text_to_audio.tasks._save_openai_usage_stats"):
                    process_article(self.article.id)

                # Verify speed was clamped correctly
                call_args = mock_speech_create.call_args[1]
                self.assertEqual(call_args["speed"], expected_speed)

                # Reset mocks for next iteration
                MockOpenAIClient.reset_mock()

    @patch("text_to_audio.tasks.ChunkToneService")
    @patch("text_to_audio.tasks.AudioSegment.from_mp3")
    @patch("text_to_audio.tasks.AudioSegment.empty")
    @override_settings(ENABLE_CHUNK_TONE_LLM=True)
    def test_process_article_speed_clamping_chunk_tone(
        self,
        mock_audio_empty,
        mock_audio_from_mp3,
        MockChunkToneService,
        MockOpenAIClient,
    ):
        """Test that speed is clamped correctly in ChunkTone path."""
        # Test boundary values
        test_cases = [
            (0.2, 0.25),  # Below minimum
            (4.5, 4.0),  # Above maximum
            (2.5, 2.5),  # In range
        ]

        for input_speed, expected_speed in test_cases:
            with self.subTest(input_speed=input_speed, expected_speed=expected_speed):
                # Set article speed
                self.article.speed = input_speed
                self.article.save()

                # Configure ChunkToneService mock
                from text_to_audio.schemas.chunk_tone import (
                    ChunkData,
                    ChunkTonePayload,
                    TTSVoice,
                )

                mock_chunk_tone_instance = MockChunkToneService.return_value
                mock_chunk_tone_instance.get_payload.return_value = ChunkTonePayload(
                    chunks=[
                        ChunkData(text="Test chunk text", voice=TTSVoice(voice="alloy"))
                    ]
                )

                # Configure OpenAI mocks
                mock_openai_instance = MockOpenAIClient.return_value
                mock_speech_create = mock_openai_instance.audio.speech.create
                mock_tts_response = MagicMock()
                mock_tts_response.stream_to_file.side_effect = (
                    self.create_dummy_file_side_effect
                )
                mock_speech_create.return_value = mock_tts_response

                mock_audio_segment = MagicMock()
                mock_audio_segment.set_frame_rate.return_value = mock_audio_segment
                mock_audio_segment.export.side_effect = (
                    self.create_dummy_file_side_effect
                )
                mock_audio_from_mp3.return_value = mock_audio_segment
                mock_audio_empty.return_value = MagicMock()

                # Process article
                with patch("text_to_audio.tasks._save_openai_usage_stats"):
                    process_article(self.article.id)

                # Verify speed was clamped correctly
                call_args = mock_speech_create.call_args[1]
                self.assertEqual(call_args["speed"], expected_speed)

                # Reset mocks for next iteration
                MockOpenAIClient.reset_mock()
                MockChunkToneService.reset_mock()


class SpeedClampingUnitTests(TestCase):
    """Unit tests for the _clamp_tts_speed function."""

    def test_clamp_tts_speed_below_minimum(self):
        """Test clamping speeds below minimum."""
        self.assertEqual(_clamp_tts_speed(0.0), 0.25)
        self.assertEqual(_clamp_tts_speed(0.1), 0.25)
        self.assertEqual(_clamp_tts_speed(0.24), 0.25)
        self.assertEqual(_clamp_tts_speed(-1.0), 0.25)

    def test_clamp_tts_speed_above_maximum(self):
        """Test clamping speeds above maximum."""
        self.assertEqual(_clamp_tts_speed(4.1), 4.0)
        self.assertEqual(_clamp_tts_speed(5.0), 4.0)
        self.assertEqual(_clamp_tts_speed(10.0), 4.0)

    def test_clamp_tts_speed_in_range(self):
        """Test speeds within valid range remain unchanged."""
        self.assertEqual(_clamp_tts_speed(0.25), 0.25)  # Min boundary
        self.assertEqual(_clamp_tts_speed(1.0), 1.0)  # Normal speed
        self.assertEqual(_clamp_tts_speed(2.5), 2.5)  # Mid-range
        self.assertEqual(_clamp_tts_speed(4.0), 4.0)  # Max boundary


# To run these tests: python manage.py test text_to_audio.tests.test_tasks


from datetime import timedelta

from django.utils import timezone
from django.conf import settings as django_settings

from text_to_audio.tasks import check_stale_articles


class CheckStaleArticlesTests(TestCase):
    """Tests for the check_stale_articles task."""

    def setUp(self):
        """Set up test data and environment for each test."""
        self.user = User.objects.create_user(
            username="staletestuser", password="password"
        )
        self.feed = Feed.objects.create(user=self.user, name="Stale Test Feed")

        # Mock ARTICLE_PROCESSING_TIMEOUT_SECONDS
        self.mock_timeout_seconds = 60
        self.settings_patcher = patch.object(
            django_settings,
            "ARTICLE_PROCESSING_TIMEOUT_SECONDS",
            self.mock_timeout_seconds,
        )
        self.settings_patcher.start()

        # Mock celery app control revoke
        self.revoke_patcher = patch("rss_tts.celery.app.control.revoke")
        self.mock_revoke = self.revoke_patcher.start()

    def tearDown(self):
        """Clean up after each test."""
        self.settings_patcher.stop()
        self.revoke_patcher.stop()
        # Clean up any created articles, feeds, users if necessary
        Article.objects.all().delete()
        Feed.objects.filter(user=self.user).delete()
        self.user.delete()


    def test_check_stale_articles_logic(self):
        """Test that stale articles are correctly identified and processed."""
        now = timezone.now()
        very_old_time = now - timedelta(seconds=self.mock_timeout_seconds * 2)
        recent_time = now - timedelta(seconds=self.mock_timeout_seconds // 2)

        stale_article = Article.objects.create(
            feed=self.feed,
            title="Stale Article",
            text_content="This article should time out.",
            status=Article.PROCESSING,
            celery_task_id="fake_stale_task_id",
            updated_at=very_old_time,
        )
        # Manually set updated_at as save() would update it
        Article.objects.filter(pk=stale_article.pk).update(updated_at=very_old_time)
        stale_article.refresh_from_db()


        recent_processing_article = Article.objects.create(
            feed=self.feed,
            title="Recent Processing Article",
            text_content="This article is still processing.",
            status=Article.PROCESSING,
            celery_task_id="fake_recent_task_id",
            updated_at=recent_time,
        )
        Article.objects.filter(pk=recent_processing_article.pk).update(updated_at=recent_time)
        recent_processing_article.refresh_from_db()

        completed_article = Article.objects.create(
            feed=self.feed,
            title="Completed Article",
            text_content="This article is completed.",
            status=Article.COMPLETED,
            updated_at=very_old_time, # old but completed
        )
        Article.objects.filter(pk=completed_article.pk).update(updated_at=very_old_time)
        completed_article.refresh_from_db()

        failed_article_already = Article.objects.create(
            feed=self.feed,
            title="Already Failed Article",
            text_content="This article already failed.",
            status=Article.FAILED,
            updated_at=very_old_time, # old but already failed
        )
        Article.objects.filter(pk=failed_article_already.pk).update(updated_at=very_old_time)
        failed_article_already.refresh_from_db()

        # Call the task
        check_stale_articles()

        # Refresh articles from DB
        stale_article.refresh_from_db()
        recent_processing_article.refresh_from_db()
        completed_article.refresh_from_db()
        failed_article_already.refresh_from_db()

        # Assertions for stale_article
        self.assertEqual(stale_article.status, Article.FAILED)
        self.assertIn("timed out", stale_article.error_message.lower())
        self.assertIsNone(stale_article.celery_task_id)
        self.mock_revoke.assert_called_once_with(
            "fake_stale_task_id", terminate=True
        )

        # Assertions for recent_processing_article
        self.assertEqual(recent_processing_article.status, Article.PROCESSING)
        self.assertIsNone(recent_processing_article.error_message) # Should not have error

        # Assertions for completed_article
        self.assertEqual(completed_article.status, Article.COMPLETED)

        # Assertions for failed_article_already
        self.assertEqual(failed_article_already.status, Article.FAILED)
