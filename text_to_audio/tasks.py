"""Celery tasks for processing articles."""

# mypy: disable-error-code="attr-defined"

from __future__ import annotations

import logging
import os
import time  # Added for timing API calls
import traceback
import uuid
from datetime import timedelta
from pathlib import Path

import openai
from celery import shared_task  # type: ignore
from django.conf import settings
from django.utils import timezone
from pydub import AudioSegment  # type: ignore

from rss_tts.celery import app as celery_app  # For task revocation

import feedparser

from .models import (
    Article,
    FollowedFeed,
)  # Import OpenAIUsageStats in helper method
from .services.content_analysis import ContentAnalysisService
from .services.user_preferences import UserPreferencesService
from .services.voice_configuration import VoiceConfigurationService
from .utils import process_url_to_text

# Configure logging
logger = logging.getLogger(__name__)


def _save_openai_usage_stats(
    user,
    article,
    article_id,
    chunk_index,
    tokens_used,
    processing_time_ms,
    word_count,
):
    """Save OpenAI usage statistics in a separate function to isolate errors.

    Args:
        user: The user who made the request
        article: The article being processed
        article_id: The ID of the article
        chunk_index: The index of the text chunk being processed
        tokens_used: Number of tokens used
        processing_time_ms: Processing time in milliseconds
        word_count: Number of words in the chunk
    """
    try:
        from django.db import transaction

        from .models import OpenAIUsageStats

        # Use transaction.atomic to ensure DB operations are isolated
        with transaction.atomic():
            OpenAIUsageStats.objects.create(
                user=user,
                article=article,
                tokens_used=tokens_used,
                processing_time_ms=processing_time_ms,
                word_count=word_count,
            )
            logger.info(
                f"OpenAI usage stats recorded for article {article_id}, "
                f"chunk {chunk_index}"
            )
    except Exception as stats_exc:
        logger.error(
            f"Failed to save OpenAIUsageStats for article {article_id}, "
            f"chunk {chunk_index}: {stats_exc}"
        )


def _chunk_text(text: str, max_length: int = 4000) -> tuple[bool, list[str]]:
    """Split text into chunks for TTS processing.

    Prioritizes natural breaks in this order:
    1. Line breaks
    2. Periods, exclamation points, question marks (sentence boundaries)
    3. Semicolons and commas (clause boundaries)
    4. Spaces (word boundaries)
    5. As a last resort, forces splits within words

    Returns:
        tuple: (success, chunks)
            - success (bool): True if all splits were at natural boundaries,
                             False if forced to split words
            - chunks (list): List of text chunks, each <= max_length
    """
    logger.debug(
        f"_chunk_text called with text of len {len(text)} and max_length {max_length}"
    )

    if not text:
        return True, []

    # Check if the entire text fits within max_length
    if len(text) <= max_length:
        return True, [text]

    chunks = []
    perfect_split = True  # Track if we had to force-split any words

    # First split by line breaks
    lines = text.split("\n")
    line_chunks = []

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # If line fits, add it directly
        if len(line) <= max_length:
            line_chunks.append(line)
        else:
            # Split line by sentence boundaries
            sentences = []
            current_sentence = ""

            # Find sentence breaks - periods, exclamation marks, question marks
            i = 0
            while i < len(line):
                current_sentence += line[i]

                # Check for sentence end
                if (
                    i < len(line) - 1
                    and line[i] in [".", "!", "?"]
                    and line[i + 1].isspace()
                ):
                    sentences.append(current_sentence.strip())
                    current_sentence = ""
                    # Skip the space
                    i += 2
                    continue
                i += 1

            # Add any remaining sentence fragment
            if current_sentence:
                sentences.append(current_sentence.strip())

            # Process each sentence
            for sentence in sentences:
                if len(sentence) <= max_length:
                    line_chunks.append(sentence)
                else:
                    # Split sentence by semicolons and commas
                    clause_chunks = []
                    clauses = []

                    # First split by semicolons
                    semi_parts = sentence.split(";")

                    for part in semi_parts:
                        part = part.strip()
                        if len(part) <= max_length:
                            clauses.append(part)
                        else:
                            # Split by commas
                            comma_parts = part.split(",")
                            for comma_part in comma_parts:
                                comma_part = comma_part.strip()
                                if comma_part:
                                    clauses.append(comma_part)

                    # Process each clause
                    for clause in clauses:
                        if len(clause) <= max_length:
                            clause_chunks.append(clause)
                        else:
                            # Build word by word
                            words = clause.split()
                            current_chunk = ""

                            for word in words:
                                # Store chunk if next word would exceed max_length
                                if len(current_chunk) + len(word) + 1 > max_length:
                                    if current_chunk:
                                        clause_chunks.append(current_chunk)

                                    # If word is too long, must force-split it
                                    if len(word) > max_length:
                                        perfect_split = False
                                        # Split the word into chunks of max_length
                                        for i in range(0, len(word), max_length):
                                            clause_chunks.append(
                                                word[i : i + max_length]
                                            )
                                        current_chunk = ""
                                    else:
                                        current_chunk = word
                                else:
                                    if current_chunk:
                                        current_chunk += " " + word
                                    else:
                                        current_chunk = word

                            # Add any remaining chunk
                            if current_chunk:
                                clause_chunks.append(current_chunk)

                    line_chunks.extend(clause_chunks)

    # Final filtering and sanity check
    chunks = [chunk for chunk in line_chunks if chunk]

    # Verify all chunks are within max_length
    for chunk in chunks:
        if len(chunk) > max_length:
            perfect_split = False

    return perfect_split, chunks


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def process_article(self, article_id: int) -> str:
    """Process an article's text_content to generate an MP3 audio file.

    Handles text chunking, TTS conversion via OpenAI, and audio stitching.
    """
    try:
        article = Article.objects.get(id=article_id)
    except Article.DoesNotExist:
        logger.error(f"Article with ID {article_id} not found.")
        return f"Article {article_id} not found."

    article.status = Article.PROCESSING
    article.save(update_fields=["status"])

    logger.info(f"Starting processing for Article ID: {article_id}")
    generated_audio_files: list[Path] = []  # Holds all generated audio pieces for final stitching
    final_audio_path: Path | None = None
    
    # Initialize OpenAI client and user once
    client = openai.OpenAI(api_key=settings.OPENAI_API_KEY)
    user = article.feed.user # For _save_openai_usage_stats

    try:
        # Ensure media directory exists
        media_root = Path(settings.MEDIA_ROOT)
        article_media_dir = media_root / "articles"
        article_media_dir.mkdir(parents=True, exist_ok=True)

        # Generate a UUID for the article audio file if not already set
        if not article.audio_uuid:
            article.audio_uuid = uuid.uuid4()
            article.save(update_fields=["audio_uuid"]) # Save immediately if other parts rely on it

        # If article has a source_url but no text_content, fetch and extract content
        if article.source_url and not article.text_content:
            logger.info(
                f"Fetching content from URL: {article.source_url} "
                f"for Article ID: {article_id}"
            )
            success, extracted_text, error = process_url_to_text(article.source_url)

            if not success or not extracted_text:
                error_msg = error or "Unknown error during URL content extraction"
                logger.error(
                    f"Failed to extract content from URL {article.source_url}: "
                    f"{error_msg}"
                )

                # Store the user-friendly error message in the database
                article.status = Article.FAILED
                article.error_message = error_msg
                article.save(update_fields=["status", "error_message"])

                # Don't retry if it's a "permanent" error like 404/403
                if error and any(code in error for code in ["404", "403"]):
                    logger.info(
                        f"Not retrying permanent error for Article ID: {article_id}"
                    )
                    return f"Failed to process Article {article_id}: {error_msg}"

                # Otherwise, let the normal retry mechanism handle it
                raise ValueError(f"Failed to extract content from URL: {error_msg}")

            # Update the article with extracted text
            article.text_content = extracted_text
            article.save(update_fields=["text_content"])
            logger.info(
                f"Successfully extracted {len(extracted_text)} characters "
                f"from URL for Article ID: {article_id}"
            )

        if not article.text_content: # This check is crucial
            logger.error(f"Article {article_id} has no text_content after potential URL fetch.")
            raise ValueError("Article text_content is empty.")

        # Analyze content to get multi-voice data.
        # This is done before TTS generation.
        # The result will be stored in article.multi_voice_data.
        # If this step fails or if the data is invalid, we will fall back to single-voice generation.
        if article.text_content: # Only proceed if there's text content
            try:
                logger.info(f"Performing content analysis for Article ID: {article_id} to get multi-voice data.")
                content_service = ContentAnalysisService()
                
                # Use a sample of the text for analysis if it's too long
                # The full text is used for actual TTS, analysis_text_sample is for the LLM prompt
                analysis_text_sample = article.text_content[:2000] if len(article.text_content) > 2000 else article.text_content
                
                analysis_result_json = content_service.analyze_content(
                    analysis_text_sample, 
                    title=article.title
                )
                
                article.multi_voice_data = analysis_result_json
                # The fields article.summary, article.detected_tone, article.voice_id, article.speed
                # are no longer directly set from this specific analysis call.
                # They might be deprecated or populated via a different mechanism if still needed.
                # For instance, a summary might be part of analysis_result_json or a separate LLM call.
                # article.voice_id and article.speed are now primarily for fallback.
                article.save(update_fields=["multi_voice_data"])
                logger.info(f"Content analysis successful, multi_voice_data updated for Article ID: {article_id}")

            except Exception as analysis_exc:
                logger.error(f"Content analysis failed for Article ID {article_id}: {analysis_exc}")
                logger.debug(traceback.format_exc())
                article.multi_voice_data = None # Ensure it's None on failure
                article.save(update_fields=["multi_voice_data"])
                # Do not re-raise here; allow fallback to single voice processing later.
        else:
            logger.warning(f"Article ID: {article_id} has no text_content. Skipping content analysis.")
            article.multi_voice_data = None
            # No need to save here if it was already None or if text_content was missing from start

        
        # --- Multi-Voice TTS Generation Attempt ---
        multi_voice_generation_successful = False
        if _is_valid_multi_voice_data(article.multi_voice_data):
            try:
                logger.info(f"Attempting multi-voice TTS generation for Article ID: {article_id}")
                voices_map = {v["name"]: v for v in article.multi_voice_data["voices"]}
                
                concatenated_multi_voice_text = ""
                for segment_idx, segment_data in enumerate(article.multi_voice_data["audio_segments"]):
                    segment_text = segment_data.get("text")
                    voice_name = segment_data.get("voice_name")

                    if not segment_text or not voice_name:
                        logger.warning(f"Invalid segment data (segment {segment_idx}) in Article {article_id}: {segment_data}. Skipping.")
                        continue
                    
                    concatenated_multi_voice_text += segment_text # For later validation

                    voice_definition = voices_map.get(voice_name)
                    if not voice_definition:
                        logger.error(f"Voice '{voice_name}' not defined in multi_voice_data for Article {article_id}, segment {segment_idx}.")
                        raise ValueError(f"Voice '{voice_name}' not defined.") # Triggers fallback

                    # Ensure tts_model is actually the OpenAI voice name like "alloy", "echo"
                    # The prompt asks for "tts_model": "string (e.g., 'alloy', 'onyx')"
                    # The API client.audio.speech.create takes `voice` parameter for this.
                    tts_api_voice = voice_definition.get("tts_model") 
                    if not tts_api_voice:
                        logger.error(f"Missing 'tts_model' for voice '{voice_name}' in Article {article_id}.")
                        raise ValueError(f"Missing 'tts_model' for voice '{voice_name}'.")

                    tts_speed = float(voice_definition.get("tts_speed", 1.0))
                    # Basic validation for speed to prevent API errors
                    if not (0.25 <= tts_speed <= 4.0):
                        logger.warning(f"Invalid TTS speed {tts_speed} for voice {voice_name}. Clamping to range [0.25, 4.0].")
                        tts_speed = max(0.25, min(tts_speed, 4.0))

                    # Chunk the segment's text if necessary
                    _, segment_text_chunks = _chunk_text(segment_text)
                    if not segment_text_chunks:
                        logger.warning(f"Segment {segment_idx} for article {article_id} ('{voice_name}') resulted in no text chunks. Skipping.")
                        continue
                    
                    logger.info(f"Processing segment {segment_idx+1}/{len(article.multi_voice_data['audio_segments'])} ('{voice_name}', {len(segment_text_chunks)} sub-chunks) for Article ID: {article_id}")

                    for chunk_idx, chunk_text in enumerate(segment_text_chunks):
                        chunk_temp_file_path = article_media_dir / f"temp_article_{article.audio_uuid}_segment_{segment_idx}_chunk_{chunk_idx}_{uuid.uuid4()}.mp3"
                        start_time = time.monotonic()
                        
                        response = client.audio.speech.create(
                            model=getattr(settings, "OPENAI_TTS_MODEL", "tts-1"), # tts-1 or tts-1-hd
                            voice=tts_api_voice, # This is 'alloy', 'echo', etc.
                            input=chunk_text,
                            speed=tts_speed
                        )
                        response.stream_to_file(chunk_temp_file_path)
                        end_time = time.monotonic()
                        processing_time_ms = int((end_time - start_time) * 1000)
                        
                        generated_audio_files.append(chunk_temp_file_path)
                        word_count = len(chunk_text.split())
                        # TODO: Improve token counting if possible from response, for now passing 0
                        _save_openai_usage_stats(user, article, article_id, f"segment_{segment_idx}_chunk_{chunk_idx}", 0, processing_time_ms, word_count)
                
                # Validate concatenated text matches original (if possible, or a large portion of it)
                # This is a basic sanity check for the LLM's segmentation.
                # The LLM prompt for ContentAnalysisService asks for this:
                # "Ensure that the concatenation of all `text` fields in `audio_segments` exactly matches the original input text."
                # However, we use a sample for analysis (first 2000 chars). So we can only validate against that sample.
                text_sample_for_validation = article.text_content[:2000] if len(article.text_content) > 2000 else article.text_content
                if not concatenated_multi_voice_text.startswith(text_sample_for_validation.strip()[:len(concatenated_multi_voice_text)-50]): # Allow some minor diff at end
                     logger.warning(f"Article {article_id}: Concatenated multi-voice text does not closely match the beginning of the original text sample. This might indicate an issue with segmentation from the LLM.")
                     # Not raising an error here, but logging it. The audio will still be generated.

                if not generated_audio_files: # Check if any audio files were actually created
                    logger.warning(f"Multi-voice processing attempted for Article ID {article_id}, but no audio files were generated.")
                    # This will naturally lead to fallback if multi_voice_generation_successful remains False
                else:
                    multi_voice_generation_successful = True
                    logger.info(f"Multi-voice TTS generation successful for Article ID: {article_id}, {len(generated_audio_files)} audio pieces generated.")

            except Exception as mv_exc:
                logger.error(f"Multi-voice TTS generation failed for Article ID {article_id}: {mv_exc}")
                logger.debug(traceback.format_exc())
                # Clean up any partially generated multi-voice files before fallback
                for temp_file in generated_audio_files:
                    if temp_file.exists(): os.remove(temp_file)
                generated_audio_files = [] # Reset for fallback
                multi_voice_generation_successful = False # Ensure fallback is triggered
        else:
            logger.info(f"Skipping multi-voice generation for Article ID: {article_id} due to missing or invalid multi_voice_data.")

        # --- Fallback to Single-Voice Generation ---
        if not multi_voice_generation_successful:
            logger.info(f"Falling back to single-voice TTS generation for Article ID: {article_id}")
            
            # Ensure any previous (failed multi-voice) temp files are cleared
            if generated_audio_files: # Should be empty if mv_exc occurred and was handled
                logger.warning(f"Clearing {len(generated_audio_files)} residual files before fallback.")
                for temp_file in generated_audio_files:
                    if temp_file.exists(): os.remove(temp_file)
                generated_audio_files = []

            text_for_audio = article.text_content 
            if article.title:
                text_for_audio = f"{article.title}.\n\n{article.text_content}"

            _, text_chunks = _chunk_text(text_for_audio)
            if not text_chunks:
                raise ValueError("No text chunks generated from text_content for single-voice fallback.")

            logger.info(f"Generated {len(text_chunks)} chunks for single-voice fallback (Article ID: {article_id})")
            
            fallback_voice = article.voice_id or getattr(settings, "OPENAI_TTS_VOICE", "alloy")
            fallback_speed = article.speed or 1.0
            # Note: article.voice_id and article.speed might not be populated if the primary analysis
            # path only sets multi_voice_data. These fields should ideally be populated by user preferences
            # or a simpler, separate analysis if multi-voice fails or is not applicable.
            # For now, this relies on them being potentially set or using global defaults.
            logger.info(f"Fallback voice: {fallback_voice}, speed: {fallback_speed} for Article ID: {article_id}")

            for i, chunk in enumerate(text_chunks):
                temp_file_path = article_media_dir / f"temp_article_{article.audio_uuid}_fallback_chunk_{i}_{uuid.uuid4()}.mp3"
                start_time = time.monotonic()
                response = client.audio.speech.create(
                    model=getattr(settings, "OPENAI_TTS_MODEL", "tts-1"),
                    voice=fallback_voice,
                    input=chunk,
                    speed=fallback_speed,
                )
                response.stream_to_file(temp_file_path)
                end_time = time.monotonic()
                processing_time_ms = int((end_time - start_time) * 1000)
                
                generated_audio_files.append(temp_file_path)
                word_count = len(chunk.split())
                # TODO: Improve token counting if possible from response
                _save_openai_usage_stats(user, article, article_id, f"fallback_chunk_{i}", 0, processing_time_ms, word_count)

            if not generated_audio_files: # Should not happen if text_chunks is not empty
                raise ValueError("Single-voice fallback processing attempted but no audio files were generated.")
            logger.info(f"Single-voice fallback TTS generation successful for Article ID: {article_id}, {len(generated_audio_files)} audio pieces generated.")

        # --- Audio Stitching and Finalization (Common for both paths) ---
        if not generated_audio_files:
            raise ValueError("No audio files were generated by any TTS process. Cannot proceed.")

        final_audio_path = article_media_dir / f"{article.audio_uuid}.mp3"
        
        feed_name = "My Podcast" # Default
        if article.feed and article.feed.name:
            feed_name = article.feed.name
        
        tags_dict = {"title": article.title or "Untitled Article", "artist": feed_name, "album": feed_name}
        export_parameters = ["-id3v2_version", "3", "-write_id3v1", "1"]

        if len(generated_audio_files) == 1:
            single_audio_path = generated_audio_files[0]
            # It's safer to copy/process the file rather than renaming, then clean up.
            # For single files, we still re-export to apply tags and ensure format.
            audio_segment = AudioSegment.from_mp3(single_audio_path)
            audio_segment = audio_segment.set_frame_rate(44100) # Ensure consistent frame rate
            audio_segment.export(final_audio_path, format="mp3", bitrate="128k", tags=tags_dict, parameters=export_parameters)
            logger.info(f"Processed single audio file and exported to {final_audio_path}")
        else:
            combined_audio = AudioSegment.empty()
            for temp_file_path_item in generated_audio_files:
                try:
                    segment_audio = AudioSegment.from_mp3(temp_file_path_item)
                    combined_audio += segment_audio
                except Exception as e: # Catch specific pydub errors if known
                    logger.error(f"Pydub error processing chunk {temp_file_path_item} for article {article_id}: {e}")
                    # Decide if this should raise immediately or try to continue with other segments
                    raise ValueError(f"Failed to process audio chunk {temp_file_path_item.name}: {e}") from e
            
            if combined_audio.duration_seconds > 0:
                combined_audio = combined_audio.set_frame_rate(44100) # Ensure consistent frame rate
                combined_audio.export(final_audio_path, format="mp3", bitrate="128k", tags=tags_dict, parameters=export_parameters)
                logger.info(f"Combined {len(generated_audio_files)} audio files and exported to {final_audio_path}")
            else:
                # This case should ideally be prevented by checks earlier (e.g., if generated_audio_files is empty)
                raise ValueError("Combined audio is empty or has zero duration, cannot export.")

        article.audio_file_path = str(final_audio_path.relative_to(media_root))
        article.status = Article.COMPLETED
        article.error_message = None # Clear any previous error
        # Save multi_voice_data again in case it was changed (e.g. by validation/cleaning, though not implemented here)
        # or to ensure it's persisted if it was valid and used.
        article.save(update_fields=["audio_file_path", "status", "error_message", "multi_voice_data"]) 
        logger.info(f"Successfully processed Article ID: {article_id}. Audio at: {article.audio_file_path}")
        return f"Article {article_id} processed successfully."

    except Exception as e:
        logger.error(f"Unhandled error processing Article ID {article_id}: {e}")
        detailed_error = traceback.format_exc()
        logger.error(detailed_error)

        article.status = Article.FAILED
        article.error_message = f"{type(e).__name__}: {e}\n{detailed_error[:1000]}"
        # Persist multi_voice_data even on failure, as it might be useful for debugging
        article.save(update_fields=["status", "error_message", "multi_voice_data"]) 

        # Celery retry mechanism
        try:
            # self.request.retries is only available if bind=True
            if hasattr(self, "request") and self.request.retries < self.max_retries:
                current = self.request.retries + 1
                logger.info(f"Retry {current}/{self.max_retries} for #{article_id}")
                raise self.retry(
                    exc=e,
                    countdown=int(self.default_retry_delay * (2**self.request.retries)),
                )
            else:
                logger.error(
                    f"Max retries reached for article {article_id}. Task failed."
                )
        # If task is called directly without Celery context (e.g. in tests)
        except AttributeError:
            logger.warning(
                "Task not executed in Celery worker context, retry unavailable."
            )

        return f"Failed to process Article {article_id}: {e}"

    finally:
        # Clean up all temporary audio files collected in generated_audio_files list
        for temp_file_path_item in generated_audio_files:
            if temp_file_path_item.exists():
                try:
                    os.remove(temp_file_path_item)
                    logger.debug(f"Cleaned up temporary file: {temp_file_path_item}")
                except OSError as e:
                    logger.error(f"Error deleting temporary file {temp_file_path_item}: {e}")


def _is_valid_multi_voice_data(data: dict | None) -> bool:
    """Validate the basic structure of multi_voice_data."""
    if not isinstance(data, dict):
        logger.debug("multi_voice_data is not a dict or is None.")
        return False
    if "voices" not in data or "audio_segments" not in data:
        logger.debug("multi_voice_data missing 'voices' or 'audio_segments' keys.")
        return False
    if not isinstance(data["voices"], list) or not isinstance(data["audio_segments"], list):
        logger.debug("'voices' or 'audio_segments' is not a list.")
        return False
    if not data["voices"]: # Must have at least one voice defined
        logger.debug("'voices' list is empty.")
        return False
    if not data["audio_segments"]: # Must have at least one segment
        logger.debug("'audio_segments' list is empty.")
        return False
    
    # Check structure of first voice definition (sample check)
    first_voice = data["voices"][0]
    if not all(k in first_voice for k in ["name", "tone", "tts_model", "tts_speed"]):
        logger.debug("First voice definition in 'voices' list is missing required keys.")
        return False
        
    # Check structure of first audio segment (sample check)
    first_segment = data["audio_segments"][0]
    if not all(k in first_segment for k in ["text", "voice_name"]):
        logger.debug("First audio segment in 'audio_segments' list is missing required keys.")
        return False
        
    return True

@shared_task
def check_stale_articles():
    """Check for articles stuck in PROCESSING and mark them as FAILED."""
    try:
        timeout_seconds = settings.ARTICLE_PROCESSING_TIMEOUT_SECONDS
    except AttributeError:
        # Fallback if the setting is not defined, though it should be.
        logger.warning(
            "ARTICLE_PROCESSING_TIMEOUT_SECONDS not set in Django settings. "
            "Defaulting to 3600 seconds (1 hour)."
        )
        timeout_seconds = 3600

    timeout_delta = timedelta(seconds=timeout_seconds)
    cutoff_time = timezone.now() - timeout_delta

    stale_articles = Article.objects.filter(
        status=Article.PROCESSING, updated_at__lt=cutoff_time
    )

    if stale_articles.exists():
        logger.info(f"Found {stale_articles.count()} stale articles to mark as FAILED.")
        for article in stale_articles:
            task_id = article.celery_task_id
            article.status = Article.FAILED
            article.error_message = (
                f"Processing timed out after {timeout_seconds} seconds "
                f"since last update at "
                f"{article.updated_at.strftime('%Y-%m-%d %H:%M:%S %Z')}."
            )
            article.celery_task_id = None  # Clear the old task ID

            try:
                article.save()
                logger.info(
                    f"Marked article {article.pk} "
                    f"(URL: {article.source_url or 'N/A'}) as FAILED due to timeout. "
                    f"Last update was at {article.updated_at}."
                )

                if task_id:
                    try:
                        celery_app.control.revoke(task_id, terminate=True)
                        logger.info(
                            f"Attempted to revoke Celery task {task_id} "
                            f"for timed-out article {article.pk}."
                        )
                    except Exception as revoke_exc:
                        logger.warning(
                            f"Failed to revoke Celery task {task_id} "
                            f"for article {article.pk}: {revoke_exc}"
                        )
            except Exception as save_exc:
                logger.error(
                    f"Failed to mark article {article.pk} as FAILED: {save_exc}"
                )
    else:
        logger.debug("No stale articles found.")

    return f"Checked for stale articles older than {timeout_seconds} seconds."


@shared_task
def poll_followed_feeds():
    """
    Polls all active FollowedFeed instances for new articles and creates Article objects.
    """
    logger.info("Starting polling of followed feeds.")

    active_feeds = FollowedFeed.objects.filter(is_active=True)
    if not active_feeds:
        logger.info("No active feeds to poll.")
        return "No active feeds to poll."

    for followed_feed in active_feeds:
        logger.info(f"Polling feed: {followed_feed.url} for user {followed_feed.user.username}")
        try:
            parsed_feed = feedparser.parse(followed_feed.url)
        except Exception as e:
            logger.error(f"Error parsing feed {followed_feed.url}: {e}")
            continue  # Skip to the next feed

        if parsed_feed.bozo:
            logger.warning(
                f"Feed {followed_feed.url} may be ill-formed. Bozo bit set with reason: {parsed_feed.bozo_exception}"
            )
            # Continue processing despite potential issues, feedparser often handles them.

        if not parsed_feed.entries:
            logger.info(f"No entries found in feed: {followed_feed.url}")
            followed_feed.last_checked = timezone.now()
            followed_feed.save(update_fields=["last_checked"])
            continue

        # Determine the GUID of the last processed entry
        last_processed_guid = followed_feed.last_guid
        new_entries_to_process = []

        if last_processed_guid:
            entry_guids = [entry.get("id", entry.get("link")) for entry in parsed_feed.entries]
            try:
                last_processed_index = entry_guids.index(last_processed_guid)
                # Process entries newer than the last processed one
                new_entries_to_process = parsed_feed.entries[:last_processed_index]
                logger.info(f"Found last processed GUID {last_processed_guid}. Processing {len(new_entries_to_process)} new entries.")
            except ValueError:
                # Last GUID not found, likely means old entries were removed from feed
                logger.warning(
                    f"Last processed GUID {last_processed_guid} not found in current feed {followed_feed.url}. "
                    f"Processing all entries (up to a limit if implemented)."
                )
                # As a safety, process all entries or a recent subset (e.g., last 10)
                # For now, processing all if GUID not found, assuming they are new or feed changed.
                new_entries_to_process = parsed_feed.entries # Or parsed_feed.entries[:10]
        else:
            # No last_guid, process all entries (or a reasonable limit)
            logger.info(f"No last_guid for {followed_feed.url}. Processing all entries.")
            new_entries_to_process = parsed_feed.entries # Or parsed_feed.entries[:10]

        # Reverse to process oldest new entry first, so last_guid is the newest
        new_entries_to_process.reverse() 
        
        latest_entry_guid_for_this_poll = None

        for entry in new_entries_to_process:
            entry_guid = entry.get("id", entry.get("link"))
            if not entry_guid:
                logger.warning(f"Skipping entry with no GUID or link in feed {followed_feed.url}")
                continue

            title = entry.get("title", "Untitled Article")
            link = entry.get("link")

            text_content = None
            # Try to get full content if available
            if "content" in entry and entry.content:
                # content can be a list of content objects
                text_content = entry.content[0].value
            elif "summary_detail" in entry and entry.summary_detail and entry.summary_detail.type == "text/html":
                text_content = entry.summary_detail.value
            elif "summary" in entry:
                text_content = entry.summary
            
            # If content is still None and link is available, fetch from URL
            if not text_content and link:
                logger.info(f"No direct content for '{title}'. Fetching from URL: {link}")
                try:
                    success, extracted_text, error_msg = process_url_to_text(link)
                    if success and extracted_text:
                        text_content = extracted_text
                        logger.info(f"Successfully extracted content for '{title}' from {link}")
                    else:
                        logger.error(f"Failed to extract content for '{title}' from {link}: {error_msg}")
                        # Optionally skip this entry or create it without text_content if allowed
                        continue # Skip this entry
                except Exception as url_proc_exc:
                    logger.error(f"Exception during process_url_to_text for {link}: {url_proc_exc}")
                    continue # Skip this entry
            elif not text_content and not link:
                 logger.warning(f"Skipping entry '{title}' as it has no content and no link.")
                 continue


            if not text_content:
                logger.warning(f"Skipping entry '{title}' from {followed_feed.url} due to missing text content after all attempts.")
                continue

            try:
                new_article = Article.objects.create(
                    feed=followed_feed.destination_feed,
                    title=title,
                    source_url=link,
                    text_content=text_content,
                    status=Article.PROCESSING, # Assuming PROCESSING status kicks off TTS
                    # Other fields like voice can be set to defaults or user preferences later
                )
                logger.info(f"Created new Article: {new_article.id} - '{new_article.title}' from feed {followed_feed.url}")
                
                # Enqueue for TTS processing
                process_article.delay(new_article.id)
                logger.info(f"Enqueued process_article task for Article ID: {new_article.id}")

                latest_entry_guid_for_this_poll = entry_guid

            except Exception as article_create_exc:
                logger.error(f"Error creating Article for entry '{title}' from {followed_feed.url}: {article_create_exc}")
                # Potentially log traceback for debugging
                # continue to next entry

        if latest_entry_guid_for_this_poll:
            followed_feed.last_guid = latest_entry_guid_for_this_poll
            logger.info(f"Updated last_guid for {followed_feed.url} to {latest_entry_guid_for_this_poll}")

        followed_feed.last_checked = timezone.now()
        followed_feed.save(update_fields=["last_guid", "last_checked"])
        logger.info(f"Finished polling feed: {followed_feed.url}")

    logger.info("Completed polling of followed feeds.")
    return "Polling of followed feeds completed."
