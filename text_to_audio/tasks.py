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

from .models import Article  # Import OpenAIUsageStats in helper method
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
    temp_audio_files: list[Path] = []
    final_audio_path: Path | None = None

    try:
        # Ensure media directory exists
        media_root = Path(settings.MEDIA_ROOT)
        article_media_dir = media_root / "articles"
        article_media_dir.mkdir(parents=True, exist_ok=True)

        # Generate a UUID for the article audio file if not already set
        if not article.audio_uuid:
            article.audio_uuid = uuid.uuid4()
            article.save(update_fields=["audio_uuid"])

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

        if not article.text_content:
            raise ValueError("Article text_content is empty.")

        # Prepend article title to text content for audio
        text_for_audio = article.text_content
        if article.title:
            text_for_audio = f"{article.title}.\n\n{article.text_content}"

        # Get text chunks with default max_length of 4000
        success, text_chunks = _chunk_text(text_for_audio)
        if not text_chunks:
            raise ValueError("No text chunks generated from text_content.")

        if not success:
            logger.warning(f"Article {article_id}: forced word splits required")

        logger.info(f"Generated {len(text_chunks)} chunks for Article ID: {article_id}")

        client = openai.OpenAI(api_key=settings.OPENAI_API_KEY)

        for i, chunk in enumerate(text_chunks):
            logger.debug(
                f"Processing chunk {i+1}/{len(text_chunks)} for Article: {article_id}"
            )
            temp_file_path = (
                article_media_dir
                / f"temp_article_{article_id}_chunk_{i}_{uuid.uuid4()}.mp3"
            )

            try:
                start_time = time.monotonic()
                response = client.audio.speech.create(
                    model=getattr(settings, "OPENAI_TTS_MODEL", "tts-1"),
                    voice=getattr(settings, "OPENAI_TTS_VOICE", "alloy"),
                    input=chunk,
                )
                response.stream_to_file(temp_file_path)
                end_time = time.monotonic()
                processing_time_ms = int((end_time - start_time) * 1000)

                temp_audio_files.append(temp_file_path)
                logger.debug(f"Saved audio chunk to {temp_file_path}")

                # Record OpenAI usage stats
                tokens_used = 0  # Default to 0
                try:
                    # Extract token usage from response with clear fallbacks
                    if hasattr(response, "usage") and hasattr(
                        response.usage, "total_tokens"
                    ):
                        try:
                            tokens_used = int(response.usage.total_tokens)
                        except (ValueError, TypeError):
                            logger.warning(
                                f"Invalid token value in response.usage.total_tokens "
                                f"for article {article_id}, chunk {i+1}"
                            )
                            tokens_used = 0
                    elif hasattr(response, "headers"):
                        # Try standard header names
                        headers = ["x-openai-tokens-used", "openai-tokens-used"]
                        for header_name in headers:
                            if header_name in response.headers:
                                try:
                                    tokens_used = int(response.headers[header_name])
                                    break
                                except (ValueError, TypeError):
                                    logger.warning(
                                        f"Invalid token value in header {header_name} "
                                        f"for article {article_id}, chunk {i+1}"
                                    )
                        # Log if we couldn't find token info in headers
                        if tokens_used == 0:
                            logger.warning(
                                f"No token usage found in headers for article "
                                f"{article_id}, chunk {i+1}. Headers: "
                                f"{list(response.headers.keys())[:5]}"
                            )
                    else:
                        logger.warning(
                            f"Cannot extract token usage - no usage/headers "
                            f"for article {article_id}, chunk {i+1}"
                        )
                except Exception as usage_exc:
                    logger.error(
                        f"Error extracting tokens for article {article_id}, "
                        f"chunk {i+1}: {usage_exc}"
                    )
                    tokens_used = 0

                # Save OpenAI stats separately to isolate DB errors from
                # the main audio processing flow
                word_count = len(chunk.split())
                user = article.feed.user
                # Create stats record in a separate function to isolate DB errors
                _save_openai_usage_stats(
                    user=user,
                    article=article,
                    article_id=article_id,
                    chunk_index=i + 1,
                    tokens_used=tokens_used,
                    processing_time_ms=processing_time_ms,
                    word_count=word_count,
                )

            except openai.APIError as e:
                logger.error(
                    f"OpenAI API error on chunk {i+1} " f"for article {article_id}: {e}"
                )
                # Decide if retry at chunk level or fail whole task
                # Fail task and rely on Celery's retry mechanism
                raise  # Re-raise to be caught by outer try-except

        if not temp_audio_files:
            raise ValueError("No audio files were generated from chunks.")

        # Generate a summary for the article using OpenAI
        try:
            if not article.summary and text_chunks:
                logger.info(f"Generating summary for Article ID: {article_id}")
                # Use the first chunk (or the whole text if it's small) for summary
                text_for_summary = text_chunks[0]
                # Limit to 2000 chars to avoid token limits
                if len(text_for_summary) > 2000:
                    text_for_summary = text_for_summary[:2000]

                client = openai.OpenAI(api_key=settings.OPENAI_API_KEY)
                # Add type annotation for the response to help mypy
                summary_response: openai.types.chat.ChatCompletion = (
                    client.chat.completions.create(
                        model=getattr(settings, "OPENAI_SUMMARY_MODEL", "o4-mini"),
                        messages=[
                            {
                                "role": "system",
                                "content": "Summarize articles concisely.",
                            },
                            {
                                "role": "user",
                                "content": (
                                    f"Create a 2-3 sentence summary of this article "
                                    f"titled '{article.title}':\n\n{text_for_summary}"
                                ),
                            },
                        ],
                        max_tokens=150,
                        temperature=0.3,
                    )
                )

                # Fixed the type error by properly accessing the message content
                if summary_response.choices and len(summary_response.choices) > 0:
                    summary_content = summary_response.choices[0].message.content
                    if summary_content:
                        article.summary = summary_content.strip()
                        article.save(update_fields=["summary"])
                        logger.info(f"Summary generated for Article ID: {article_id}")
                    else:
                        logger.warning(
                            f"Empty summary response for Article ID: {article_id}"
                        )
                else:
                    logger.warning(
                        f"Failed to generate summary for Article ID: {article_id}"
                    )
        except Exception as summary_exc:
            # Log but don't fail the whole process if summary generation fails
            logger.error(
                f"Error generating summary for Article ID {article_id}: {summary_exc}"
            )
            logger.debug(traceback.format_exc())
            # Continue with audio generation

        # Stitch audio files
        # Define ID3 tags and export parameters
        feed_name = "My Podcast"
        if article.feed and article.feed.name:
            feed_name = article.feed.name
        # Handle case where feed.name is explicitly None
        elif (
            hasattr(article, "feed")
            and hasattr(article.feed, "name")
            and article.feed.name is None
        ):
            feed_name = "My Podcast"

        tags_dict = {
            "title": article.title if article.title else "Untitled Article",
            "artist": feed_name,
            "album": feed_name,
        }
        export_parameters = ["-id3v2_version", "3", "-write_id3v1", "1"]

        # Save files directly as UUID.mp3 (without "article_" prefix)
        # to match Caddy's rewrite rule
        final_audio_path = article_media_dir / f"{article.audio_uuid}.mp3"

        if len(temp_audio_files) == 1:
            temp_single_audio_path = temp_audio_files[0]
            try:
                audio_segment = AudioSegment.from_mp3(temp_single_audio_path)
                audio_segment = audio_segment.set_frame_rate(44100)
                audio_segment.export(
                    final_audio_path,
                    format="mp3",
                    bitrate="128k",
                    tags=tags_dict,
                    parameters=export_parameters,
                )
                logger.info(
                    f"Processed single audio chunk and exported to {final_audio_path}"
                )
            except Exception as e:
                logger.error(
                    f"Error processing single audio chunk {temp_single_audio_path}: {e}"
                )
                fname = temp_single_audio_path.name
                error_msg = f"Failed to process single audio chunk {fname}"
                raise ValueError(f"{error_msg}: {e}") from e
        else:
            combined_audio = AudioSegment.empty()
            for temp_file in temp_audio_files:
                try:
                    segment = AudioSegment.from_mp3(temp_file)
                    combined_audio += segment
                except Exception as e:  # pydub can raise various errors
                    logger.error(
                        f"Pydub error processing chunk {temp_file} "
                        f"for article {article_id}: {e}"
                    )
                    error_msg = f"Failed to process audio chunk {temp_file.name}"
                    raise ValueError(f"{error_msg}: {e}") from e

            if combined_audio:
                combined_audio = combined_audio.set_frame_rate(44100)
                combined_audio.export(
                    final_audio_path,
                    format="mp3",
                    bitrate="128k",
                    tags=tags_dict,
                    parameters=export_parameters,
                )
                chunks_count = len(temp_audio_files)
                logger.info(
                    f"Combined {chunks_count} audio chunks "
                    f"and exported to {final_audio_path}"
                )
            else:
                raise ValueError("Combined audio is empty, cannot export.")

        article.audio_file_path = str(final_audio_path.relative_to(media_root))
        article.status = Article.COMPLETED
        article.error_message = None  # Clear any previous error
        article.save(update_fields=["audio_file_path", "status", "error_message"])
        logger.info(
            f"Processed Article ID: {article_id}. Audio at: {article.audio_file_path}"
        )
        return f"Article {article_id} processed successfully."

    except Exception as e:
        logger.error(f"Error processing Article ID {article_id}: {e}")
        detailed_error = traceback.format_exc()
        logger.error(detailed_error)

        article.status = Article.FAILED
        # Store a truncated traceback
        article.error_message = f"{type(e).__name__}: {e}\n{detailed_error[:1000]}"
        article.save(update_fields=["status", "error_message"])

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
        # Clean up temporary chunk files
        for temp_file in temp_audio_files:
            if temp_file.exists():
                try:
                    os.remove(temp_file)
                    logger.debug(f"Cleaned up temporary file: {temp_file}")
                except OSError as e:
                    logger.error(f"Error deleting temporary file {temp_file}: {e}")


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
