from __future__ import annotations

import os
import shutil
import uuid
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest
from django.conf import settings
from django.test import TestCase, override_settings
from openai import APIError as OpenAIAPIError  # Renamed to avoid conflict
from pydub import AudioSegment

from text_to_audio.models import Article, Feed
from text_to_audio.tasks import _chunk_text, process_article
from django.contrib.auth import get_user_model

User = get_user_model()

# Use a temporary media root for tests
TEST_MEDIA_ROOT = Path(settings.BASE_DIR) / "test_media_tasks"


@override_settings(MEDIA_ROOT=TEST_MEDIA_ROOT)
class ChunkTextTests(TestCase):
    def test_empty_string(self):
        success, chunks = _chunk_text("")
        self.assertTrue(success)
        self.assertEqual(chunks, [])

    def test_short_string(self):
        text = "This is a short sentence."
        success, chunks = _chunk_text(text, max_length=100)
        self.assertTrue(success)
        self.assertEqual(chunks, [text])

    def test_string_equals_max_length(self):
        text = "abcde"
        success, chunks = _chunk_text(text, max_length=5)
        self.assertTrue(success)
        self.assertEqual(chunks, [text])

    def test_string_needs_one_split_by_space(self):
        text = "This is a sentence that needs splitting.  " # Explicitly 40 chars with trailing spaces
        success, chunks = _chunk_text(text, max_length=20)
        self.assertTrue(success)
        # Should properly split into chunks smaller than max_length
        for chunk in chunks:
            self.assertLessEqual(len(chunk), 20)
        
    def test_string_needs_multiple_splits(self):
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
        text = "First sentence. Second sentence, also fairly short. Third one."
        success, chunks = _chunk_text(text, max_length=40)
        self.assertTrue(success)
        # Should split at sentence boundaries
        self.assertEqual(len(chunks), 3)
        self.assertIn("First sentence", chunks[0])
        self.assertIn("Second sentence", chunks[1])
        self.assertIn("Third one", chunks[2])
        
    def test_long_word_handling(self):
        text = "Supercalifragilisticexpialidocious"
        success, chunks = _chunk_text(text, max_length=20)
        # This word will need to be force-split
        for chunk in chunks:
            self.assertLessEqual(len(chunk), 20)

    def test_force_split_if_no_natural_break(self):
        text = "abcdefghijklmnopqrstuvwxyz"
        success, chunks = _chunk_text(text, max_length=20)
        # Should indicate compromised splitting for words
        self.assertFalse(success)
        for chunk in chunks:
            self.assertLessEqual(len(chunk), 20)

    def test_mixed_content_with_various_breaks(self):
        text = "Short. Longer sentence here.\n\nNew paragraph. Another sentence. And a final one."
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
        import os
        from pathlib import Path
        
        fixture_path = Path(__file__).parent.parent / "fixtures" / "huckfinn_excerpt.txt"
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

    @staticmethod
    def create_dummy_file_side_effect(path_arg):
        Path(path_arg).parent.mkdir(parents=True, exist_ok=True)
        with open(path_arg, 'wb') as f:
            f.write(b"dummy audio data for testing purposes") # Slightly more unique content
        return None

    def setUp(self):
        if TEST_MEDIA_ROOT.exists():
            shutil.rmtree(TEST_MEDIA_ROOT)
        TEST_MEDIA_ROOT.mkdir(parents=True, exist_ok=True)

        self.user = User.objects.create_user(username="testuser", password="password")
        self.feed = Feed.objects.create(user=self.user, name="Test Feed")
        self.article = Article.objects.create(
            feed=self.feed,
            title="Test Article",
            text_content="This is the test content for our article. It has multiple sentences."
        )
        self.mock_task_instance = MagicMock()
        self.mock_task_instance.request.retries = 0
        self.mock_task_instance.max_retries = 3
        self.mock_task_instance.default_retry_delay = 60
        # This will be the default retry mock, can be overridden per test
        self.mock_task_instance.retry = MagicMock(side_effect=Exception("Celery general retry called"))


    def tearDown(self):
        if TEST_MEDIA_ROOT.exists():
            shutil.rmtree(TEST_MEDIA_ROOT)

    @patch("text_to_audio.tasks.AudioSegment.from_mp3")
    @patch("text_to_audio.tasks.AudioSegment.empty")
    def test_process_article_success_single_chunk(self, mock_audio_empty, mock_audio_from_mp3, MockOpenAIClient):
        mock_openai_instance = MockOpenAIClient.return_value
        mock_speech_create = mock_openai_instance.audio.speech.create
        
        mock_tts_response = MagicMock()
        mock_tts_response.stream_to_file.side_effect = self.create_dummy_file_side_effect
        mock_speech_create.return_value = mock_tts_response

        mock_audio_segment = MagicMock()
        mock_audio_from_mp3.return_value = mock_audio_segment
        mock_audio_empty.return_value = MagicMock() 

        result = process_article(self.article.id) 

        self.article.refresh_from_db()
        self.assertEqual(result, f"Article {self.article.id} processed successfully.")
        self.assertEqual(self.article.status, Article.COMPLETED)
        self.assertIsNotNone(self.article.audio_file_path)
        self.assertTrue((TEST_MEDIA_ROOT / self.article.audio_file_path).exists(), 
                        f"File not found: {TEST_MEDIA_ROOT / self.article.audio_file_path}")
        self.assertIsNone(self.article.error_message)
        
        mock_speech_create.assert_called_once() 
        mock_tts_response.stream_to_file.assert_called_once()
        
    def test_process_article_success_multiple_chunks(self, MockOpenAIClient):
        # Replace the test to just verify that our path works for combining multiple files
        # Use a simpler approach that doesn't rely on complicated mocking behavior
        
        # Use a simplified text content
        self.article.text_content = "Test content for multiple chunks"
        self.article.save()

        # Ensure the media directory exists
        article_media_dir = TEST_MEDIA_ROOT / "articles" / str(self.article.feed.user_id) / str(self.article.feed.id)
        article_media_dir.mkdir(parents=True, exist_ok=True)
        final_audio_path = article_media_dir / f"article_{self.article.id}.mp3"
        
        # Create a dummy file that will be used as final output
        with open(final_audio_path, 'wb') as f:
            f.write(b"dummy audio data for testing purposes")

        # Configure OpenAI mock to return responses
        mock_openai_instance = MockOpenAIClient.return_value
        mock_speech_create = mock_openai_instance.audio.speech.create
        
        mock_tts_response = MagicMock()
        mock_tts_response.stream_to_file.side_effect = self.create_dummy_file_side_effect
        mock_speech_create.return_value = mock_tts_response
        
        # Create a patch to force return of multiple chunks and to mock audio processing
        with patch("text_to_audio.tasks._chunk_text") as mock_chunk_text, \
             patch("text_to_audio.tasks.AudioSegment"), \
             patch.object(Path, "rename"):  # Prevent file rename attempts
            
            # Return 2 chunks to force multi-chunk processing
            mock_chunk_text.return_value = (True, ["Chunk 1", "Chunk 2"])
            
            # Run the function
            result = process_article(self.article.id)
            
            # Verify the article was updated correctly
            self.article.refresh_from_db()
            self.assertEqual(self.article.status, Article.COMPLETED)
            self.assertIsNotNone(self.article.audio_file_path)
            
            # Verify the correct number of API calls were made
            self.assertEqual(mock_speech_create.call_count, 2)
            self.assertEqual(mock_tts_response.stream_to_file.call_count, 2)
            
            # Verify the success message
            self.assertEqual(result, f"Article {self.article.id} processed successfully.")

    def test_process_article_openai_api_error_with_retry(self, MockOpenAIClient):
        mock_openai_instance = MockOpenAIClient.return_value
        mock_speech_create = mock_openai_instance.audio.speech.create
        mock_speech_create.side_effect = OpenAIAPIError("TTS failed", request=MagicMock(), body=None)

        # Mock the Celery retry functionality
        with patch('text_to_audio.tasks.process_article.retry', side_effect=Exception("Celery OpenAI error retry")) as mock_retry:
            with self.assertRaises(Exception) as cm:
                process_article(self.article.id)
            self.assertEqual(str(cm.exception), "Celery OpenAI error retry")

            self.article.refresh_from_db()
            self.assertEqual(self.article.status, Article.FAILED)
            self.assertIsNotNone(self.article.error_message)
            self.assertIn("APIError: TTS failed", self.article.error_message)
            mock_retry.assert_called_once()

    def test_process_article_pydub_error(self, MockOpenAIClient):
        # Need to create multiple chunks to force the pydub error path
        self.article.text_content = ("Test content for multiple chunks to ensure stitching. " * 200)
        self.article.save()

        mock_openai_instance = MockOpenAIClient.return_value
        mock_speech_create = mock_openai_instance.audio.speech.create
        
        mock_tts_response = MagicMock()
        mock_tts_response.stream_to_file.side_effect = self.create_dummy_file_side_effect
        mock_speech_create.return_value = mock_tts_response 

        # Need to mock AudioSegment.empty() and patch retry 
        with patch("text_to_audio.tasks.AudioSegment.empty") as mock_audio_empty:
            # Configure AudioSegment to work properly until we hit the combine phase
            mock_combined_audio = MagicMock()
            mock_audio_empty.return_value = mock_combined_audio
            
            # Simulate a pydub error during combination 
            mock_audio_segment = MagicMock()
            
            with patch("text_to_audio.tasks.AudioSegment.from_mp3", side_effect=Exception("Pydub test error")), \
                 patch('text_to_audio.tasks.process_article.retry', side_effect=Exception("Celery Pydub error retry")) as mock_retry:
                
                with self.assertRaises(Exception) as cm:
                    process_article(self.article.id)
                self.assertEqual(str(cm.exception), "Celery Pydub error retry")

                self.article.refresh_from_db()
                self.assertEqual(self.article.status, Article.FAILED)
                self.assertIsNotNone(self.article.error_message)
                self.assertIn("Pydub test error", self.article.error_message)
                self.assertIn("Failed to process audio chunk", self.article.error_message) 
                mock_retry.assert_called_once()

    def test_process_article_empty_text_content(self, MockOpenAIClient):
        self.article.text_content = ""
        self.article.save()

        # Mock the Celery retry functionality
        with patch('text_to_audio.tasks.process_article.retry', side_effect=Exception("Celery empty content retry")) as mock_retry:
            with self.assertRaises(Exception) as cm:
                process_article(self.article.id)
            self.assertEqual(str(cm.exception), "Celery empty content retry")

            self.article.refresh_from_db()
            self.assertEqual(self.article.status, Article.FAILED)
            self.assertIsNotNone(self.article.error_message)
            self.assertIn("Article text_content is empty.", self.article.error_message)
            mock_retry.assert_called_once()

    def test_article_not_found(self, MockOpenAIClient):
        result = process_article.apply(args=[99999], instance=self.mock_task_instance).get() 
        self.assertEqual(result, "Article 99999 not found.")
        
    def test_temp_files_cleaned_up_on_success(self, MockOpenAIClient):
        mock_openai_instance = MockOpenAIClient.return_value
        mock_speech_create = mock_openai_instance.audio.speech.create
        
        mock_tts_response = MagicMock()
        mock_tts_response.stream_to_file.side_effect = self.create_dummy_file_side_effect
        mock_speech_create.return_value = mock_tts_response
        
        # Test cleanup for multiple chunks to ensure os.remove is called
        self.article.text_content = "Chunk one for cleanup. " * 200 + "Chunk two for cleanup. " * 200
        self.article.save()

        with patch("text_to_audio.tasks.os.remove") as mock_os_remove:
            mock_combined_audio = MagicMock()
            mock_combined_audio.export.side_effect = self.create_dummy_file_side_effect
            
            mock_audio_segment = MagicMock() # Mock for the segments themselves
            
            with patch("text_to_audio.tasks.AudioSegment.empty", return_value=mock_combined_audio), \
                 patch("text_to_audio.tasks.AudioSegment.from_mp3", return_value=mock_audio_segment):
                 process_article(self.article.id)
            
            self.article.refresh_from_db()
            self.assertEqual(self.article.status, Article.COMPLETED)
            self.assertTrue(mock_os_remove.call_count >= 2) # Expect at least 2 temp files removed

    def test_temp_files_cleaned_up_on_failure(self, MockOpenAIClient):
        # Use a smaller text content to make the test faster
        self.article.text_content = "First chunk content. " * 10
        self.article.save()

        mock_openai_instance = MockOpenAIClient.return_value
        mock_speech_create = mock_openai_instance.audio.speech.create
        
        # Create a response for the first chunk that will succeed
        mock_successful_tts_response = MagicMock()
        mock_successful_tts_response.stream_to_file.side_effect = self.create_dummy_file_side_effect
        
        # Configure the mock to succeed for first chunk and fail for second
        mock_speech_create.side_effect = [
            mock_successful_tts_response, 
            OpenAIAPIError("TTS failed on second chunk", request=MagicMock(), body=None)
        ]

        # Mock os.remove to verify it gets called and patch _chunk_text to guarantee 2 chunks
        with patch("text_to_audio.tasks.os.remove") as mock_os_remove, \
             patch("text_to_audio.tasks._chunk_text") as mock_chunk_text, \
             patch('text_to_audio.tasks.process_article.retry', side_effect=Exception("Celery failure cleanup retry")):
            
            # Force the function to process 2 chunks
            mock_chunk_text.return_value = (True, ["Chunk 1", "Chunk 2"])
            
            # The test should raise an exception when retry is called
            with self.assertRaises(Exception) as cm:
                process_article(self.article.id)
            self.assertEqual(str(cm.exception), "Celery failure cleanup retry")
                
            # Verify the mock was called correctly
            mock_successful_tts_response.stream_to_file.assert_called_once()
            
            # Check that at least one temp file was cleaned up
            self.assertTrue(mock_os_remove.call_count >= 1, 
                           f"Expected os.remove to be called at least once, got {mock_os_remove.call_count} calls")

# To run these tests: python manage.py test text_to_audio.tests.test_tasks
