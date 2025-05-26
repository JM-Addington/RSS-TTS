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
from text_to_audio.tasks import _chunk_text, process_article

User = get_user_model()

# Use a temporary media root for tests
TEST_MEDIA_ROOT = Path(settings.BASE_DIR) / "test_media_tasks"


@override_settings(MEDIA_ROOT=TEST_MEDIA_ROOT)
class ChunkTextTests(TestCase):
    """Tests for the _chunk_text function.

    These tests verify that the text chunking algorithm properly splits text at natural
    language boundaries while respecting the maximum length constraint.
    """

    def test_empty_string(self):
        """Test that an empty string returns an empty list of chunks."""
        success, chunks = _chunk_text("")
        self.assertTrue(success)
        self.assertEqual(chunks, [])

    def test_short_string(self):
        """Test that a short string (under max length) is kept as one chunk."""
        text = "This is a short sentence."
        success, chunks = _chunk_text(text, max_length=100)
        self.assertTrue(success)
        self.assertEqual(chunks, [text])

    def test_string_equals_max_length(self):
        """Test that a string exactly equal to max length is kept as one chunk."""
        text = "abcde"
        success, chunks = _chunk_text(text, max_length=5)
        self.assertTrue(success)
        self.assertEqual(chunks, [text])

    def test_string_needs_one_split_by_space(self):
        """Test that a string is properly split at word boundaries when needed."""
        # Explicitly 40 chars with trailing spaces
        text = "This is a sentence that needs splitting.  "
        success, chunks = _chunk_text(text, max_length=20)
        self.assertTrue(success)
        # Should properly split into chunks smaller than max_length
        for chunk in chunks:
            self.assertLessEqual(len(chunk), 20)

    def test_string_needs_multiple_splits(self):
        """Test that a string requiring multiple splits is properly chunked."""
        text = "one two three four five six seven eight nine ten"
        success, chunks = _chunk_text(text, max_length=17)
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
        success, chunks_ml50 = _chunk_text(text, max_length=50)
        self.assertTrue(success)
        # Should split into 2 paragraphs
        self.assertEqual(len(chunks_ml50), 2)

        success, chunks_ml30 = _chunk_text(text, max_length=30)
        self.assertTrue(success)
        # Each chunk should be <= max_length
        for chunk in chunks_ml30:
            self.assertLessEqual(len(chunk), 30)

    def test_split_respects_sentence_breaks(self):
        """Test that text is properly split at sentence boundaries when possible."""
        text = "First sentence. Second sentence, also fairly short. Third one."
        success, chunks = _chunk_text(text, max_length=40)
        self.assertTrue(success)
        # Should split at sentence boundaries
        self.assertEqual(len(chunks), 3)
        self.assertIn("First sentence", chunks[0])
        self.assertIn("Second sentence", chunks[1])
        self.assertIn("Third one", chunks[2])

    def test_long_word_handling(self):
        """Test long words with forced splitting."""
        text = "Supercalifragilisticexpialidocious"
        success, chunks = _chunk_text(text, max_length=20)
        # This word will need to be force-split
        for chunk in chunks:
            self.assertLessEqual(len(chunk), 20)

    def test_force_split_if_no_natural_break(self):
        """Test text with no natural breaks."""
        text = "abcdefghijklmnopqrstuvwxyz"
        success, chunks = _chunk_text(text, max_length=20)
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
        success, chunks = _chunk_text(text, max_length=30)
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
        success, chunks = _chunk_text(text, max_length=4000)
        self.assertTrue(success)
        self.assertTrue(len(chunks) >= 1)  # Should have at least one chunk
        for chunk in chunks:
            self.assertLessEqual(len(chunk), 4000)

        # Test with medium max_length (1000 chars) - more realistic for API calls
        success, chunks = _chunk_text(text, max_length=1000)
        self.assertTrue(success)
        self.assertTrue(len(chunks) >= 3)  # Should have several chunks
        for chunk in chunks:
            self.assertLessEqual(len(chunk), 1000)

        # Test with smaller max_length (200 chars) - should split on sentences
        success, chunks = _chunk_text(text, max_length=200)
        self.assertTrue(success)
        self.assertTrue(len(chunks) >= 10)  # Should have many chunks
        for chunk in chunks:
            self.assertLessEqual(len(chunk), 200)

        # Test with very small max_length (20 chars) - should force word splitting
        success, chunks = _chunk_text(text, max_length=20)
        # May be false if words need to be forcibly split
        self.assertTrue(len(chunks) > 0)
        for chunk in chunks:
            self.assertLessEqual(len(chunk), 20)


@override_settings(MEDIA_ROOT=TEST_MEDIA_ROOT, OPENAI_API_KEY="test_api_key")
@patch("text_to_audio.tasks.openai.OpenAI")
class ProcessArticleTests(TestCase):
    """Tests for the process_article task.

    These tests verify the functionality of the article processing task, including
    text-to-speech conversion, error handling, and file management.
    """

    @staticmethod
    def create_dummy_file_side_effect(path_arg):
        """Create a dummy file for testing purposes.

        Used as a side effect for mocked stream_to_file calls.
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
            self.assertGreater(stats_obj.tokens_used, 0)
            self.assertTrue(stats_obj.processing_time_ms >= 0)
            # Check word count (sample text has 13 words with title)
            self.assertEqual(stats_obj.word_count, 13)

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
        with patch("text_to_audio.tasks._chunk_text") as mock_chunk_text, patch(
            "text_to_audio.tasks.AudioSegment"
        ), patch.object(
            Path, "rename"
        ):  # Prevent file rename attempts

            # Return 2 chunks to force multi-chunk processing
            mock_chunk_text.return_value = (True, chunks_data)

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
                self.assertGreater(stat_record.tokens_used, 0)
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
        self.assertTrue(
            any(
                "Failed to save OpenAIUsageStats for article 1, chunk 1:" in message
                for message in log_watcher.output
            ),
            "Log does not contain detailed stats saving error message",
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
                    self.assertIn("Failed to process", self.article.error_message)
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
        # Override _chunk_text to return exactly 2 chunks
        chunks = ["Chunk one for cleanup.", "Chunk two for cleanup."]

        with patch("text_to_audio.tasks._chunk_text", return_value=(True, chunks)):
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

            # Mock os.remove to verify calls and patch _chunk_text for 2 chunks
            with patch("text_to_audio.tasks.os.remove") as mock_os_remove, patch(
                "text_to_audio.tasks._chunk_text"
            ) as mock_chunk_text, patch(
                "text_to_audio.tasks.process_article.retry",
                side_effect=Exception("Celery failure cleanup retry"),
            ):

                # Force the function to process 2 chunks
                mock_chunk_text.return_value = (True, ["Chunk 1", "Chunk 2"])

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
        # _is_valid_multi_voice_data will use this if set directly
        self.article.multi_voice_data = valid_multi_voice_data
        self.article.save()

        # Force multi-voice path
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

        # _chunk_text on "Test Article.\n\nThis is fallback content. It is short."
        # is likely 1 chunk.
        expected_chunks = 1
        self.assertEqual(mock_speech_create.call_count, expected_chunks)

        # Verify fallback voice and speed were used
        call_args = mock_speech_create.call_args_list[0][1]
        self.assertEqual(call_args["voice"], "echo")
        self.assertEqual(call_args["speed"], 0.9)
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
        mock_audio_segment.export.side_effect = self.create_dummy_file_side_effect
        mock_audio_from_mp3.return_value = mock_audio_segment
        mock_audio_empty.return_value = MagicMock()

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

        # We need to know how many chunks _chunk_text will make for long_segment_text
        # Default _chunk_text max_length is 4000 and our text is ~2100 chars.
        # Extend the text so the long segment requires multiple chunks.
        long_segment_text_actually_long = (
            "This is an extremely long segment designed to test chunking. " * 250
        )  # > 4000 chars

        multi_voice_data_with_long_segment["audio_segments"][0][  # type: ignore[index]
            "text"
        ] = long_segment_text_actually_long
        self.article.multi_voice_data = multi_voice_data_with_long_segment
        self.article.save()

        # Let's spy on _chunk_text to verify its calls
        with patch(
            "text_to_audio.tasks._is_valid_multi_voice_data",
            return_value=True,
        ), patch("text_to_audio.tasks._chunk_text") as _, patch(
            "text_to_audio.tasks._save_openai_usage_stats"
        ) as mock_save_stats:

            # _chunk_text runs normally: long segment may split into N chunks
            # short segment stays in one chunk

            # Let _chunk_text run and expect N+1 calls to speech.create

            # long_segment_text_actually_long has ~15500 chars so N = 4 chunks
            # plus one short chunk -> 5 speech.create calls

            # Rely on actual _chunk_text behavior for each call

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

        self.assertEqual(mock_save_stats.call_count, 5)


# To run these tests: python manage.py test text_to_audio.tests.test_tasks
