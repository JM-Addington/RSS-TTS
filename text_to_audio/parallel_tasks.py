"""
Celery tasks for parallel TTS processing.

This module contains the new tasks for handling parallel TTS generation:
- generate_tts_for_chunk: Processes a single text chunk
- stitch_audio_and_finalize: Combines chunks and finalizes the article
"""

import logging
import os
import tempfile
import time
import traceback
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import openai
from celery import shared_task
from django.conf import settings
from pydub import AudioSegment

from .models import Article
from .rate_limiter import get_rate_limiter

logger = logging.getLogger(__name__)


def _prepare_tts_request(
    chunk_data: Dict[str, Any], voice_config: Dict[str, Any]
) -> Dict[str, Any]:
    """Prepare TTS request data from chunk and voice configuration."""
    # Extract voice configuration
    voice_name = chunk_data.get("voice", voice_config.get("voice", "alloy"))
    if isinstance(voice_name, dict):
        voice_name = voice_name.get("voice", "alloy")

    instructions = chunk_data.get("instructions") or voice_config.get("instructions")
    speed = voice_config.get("speed", 1.0)

    # Clamp speed to valid range
    speed = max(0.25, min(speed, 4.0))

    # Prepare TTS request
    tts_model = getattr(settings, "OPENAI_TTS_MODEL", "tts-1")
    tts_request_data = {
        "model": tts_model,
        "voice": voice_name,
        "input": chunk_data.get("text", ""),
        "speed": speed,
    }

    # Add instructions parameter for supported models
    if instructions and tts_model in {"gpt-4o-mini-tts", "tts-1-hd"}:
        tts_request_data["instructions"] = instructions

    return tts_request_data


def _handle_tts_api_call(
    client,
    tts_request_data: Dict[str, Any],
    temp_file_path: Path,
    article_id: int,
    chunk_idx: int,
) -> int:
    """Handle the TTS API call and return processing time in milliseconds."""
    tts_start_time = time.monotonic()

    # Log TTS API call details
    instructions = tts_request_data.get("instructions", "")
    logger.info(
        f"TTS API Call - Article {article_id}, chunk {chunk_idx}: "
        f"model={tts_request_data['model']}, voice={tts_request_data['voice']}, "
        f"speed={tts_request_data['speed']}, text_length={len(tts_request_data['input'])} chars"
        + (f", instructions='{instructions}'" if instructions else "")
    )

    # Call TTS API with detailed logging
    response = client.audio.speech.create(**tts_request_data)
    response.stream_to_file(str(temp_file_path))

    tts_end_time = time.monotonic()
    tts_duration_ms = int((tts_end_time - tts_start_time) * 1000)

    # Log successful TTS API call
    from .utils import log_openai_api_call

    tts_response_data = {
        "status": "success",
        "audio_file_generated": True,
        "file_path": str(temp_file_path),
    }
    if hasattr(response, "headers"):
        tts_response_data["headers"] = dict(response.headers)

    log_openai_api_call(
        operation=f"TTS Generation (Parallel) - Article {article_id}, chunk {chunk_idx}",
        request_data=tts_request_data,
        response_data=tts_response_data,
        duration_ms=tts_duration_ms,
    )

    return tts_duration_ms, response


@shared_task(bind=True, max_retries=2, default_retry_delay=30)
def generate_tts_for_chunk(  # noqa: C901
    self,
    article_id: int,
    chunk_data: Dict[str, Any],
    chunk_idx: int,
    voice_config: Dict[str, Any],
) -> Tuple[int, Optional[str], Optional[str]]:
    """
    Generate TTS audio for a single text chunk.

    Args:
        article_id: ID of the article being processed
        chunk_data: Dictionary containing chunk text and voice info
        chunk_idx: Index of this chunk in the sequence
        voice_config: Voice configuration (speed, instructions, etc.)

    Returns:
        Tuple of (chunk_idx, temp_file_path, error_message)
        - If successful: (chunk_idx, temp_file_path, None)
        - If failed: (chunk_idx, None, error_message)
    """
    start_time = time.monotonic()
    temp_file_path = None

    try:
        # Get article for validation and media directory
        try:
            article = Article.objects.get(id=article_id)
        except Article.DoesNotExist:
            error_msg = f"Article {article_id} not found"
            logger.error(error_msg)
            return (chunk_idx, None, error_msg)

        # Ensure article is still processing (not cancelled)
        if article.status != Article.PROCESSING:
            error_msg = (
                f"Article {article_id} no longer processing (status: {article.status})"
            )
            logger.warning(error_msg)
            return (chunk_idx, None, error_msg)

        # Extract chunk information
        chunk_text = chunk_data.get("text", "")
        if not chunk_text:
            error_msg = f"Empty chunk text for article {article_id}, chunk {chunk_idx}"
            logger.error(error_msg)
            return (chunk_idx, None, error_msg)

        # Extract voice configuration
        voice_name = chunk_data.get("voice", voice_config.get("voice", "alloy"))
        if isinstance(voice_name, dict):
            voice_name = voice_name.get("voice", "alloy")

        instructions = chunk_data.get("instructions") or voice_config.get(
            "instructions"
        )
        speed = voice_config.get("speed", 1.0)

        # Clamp speed to valid range
        speed = max(0.25, min(speed, 4.0))

        # Rate limiting
        rate_limiter = get_rate_limiter()
        if not rate_limiter.acquire_tts_token(timeout=60.0):
            error_msg = (
                f"Rate limit timeout for article {article_id}, chunk {chunk_idx}"
            )
            logger.error(error_msg)
            # Retry with exponential backoff
            if self.request.retries < self.max_retries:
                countdown = 60 * (2**self.request.retries)
                logger.info(
                    f"Retrying chunk {chunk_idx} in {countdown}s due to rate limiting"
                )
                raise self.retry(countdown=countdown)
            return (chunk_idx, None, error_msg)

        # Prepare temporary file path
        media_root = Path(settings.MEDIA_ROOT)
        articles_dir = media_root / "articles"
        articles_dir.mkdir(exist_ok=True)

        # Use tempfile for better hygiene and collision avoidance
        temp_file = tempfile.NamedTemporaryFile(
            dir=str(articles_dir),
            suffix=".mp3",
            prefix=f"chunk_{article.audio_uuid}_{chunk_idx}_",
            delete=False,
        )
        temp_file_path = Path(temp_file.name)
        temp_file.close()  # Close so we can write to it with TTS

        # Initialize OpenAI client
        client = openai.OpenAI(api_key=settings.OPENAI_API_KEY)

        # Prepare TTS request
        tts_model = getattr(settings, "OPENAI_TTS_MODEL", "tts-1")
        tts_request_data = {
            "model": tts_model,
            "voice": voice_name,
            "input": chunk_text,
            "speed": speed,
        }

        # Add instructions parameter for supported models
        if instructions and tts_model in {"gpt-4o-mini-tts", "tts-1-hd"}:
            tts_request_data["instructions"] = instructions

        # Log TTS API call details
        logger.info(
            f"TTS Chunk {chunk_idx} API Call - Article {article_id}: "
            f"model={tts_model}, voice={voice_name}, speed={speed}, "
            f"text_length={len(chunk_text)} chars"
            + (f", instructions='{instructions}'" if instructions else "")
        )

        # Call TTS API with detailed logging
        tts_start_time = time.monotonic()
        try:
            response = client.audio.speech.create(**tts_request_data)
            response.stream_to_file(temp_file_path)
            tts_end_time = time.monotonic()
            tts_duration_ms = int((tts_end_time - tts_start_time) * 1000)

            # Log successful TTS API call
            from .utils import log_openai_api_call

            tts_response_data = {
                "status": "success",
                "audio_file_generated": True,
                "file_path": str(temp_file_path),
                "chunk_idx": chunk_idx,
            }

            if hasattr(response, "headers"):
                tts_response_data["headers"] = dict(response.headers)

            log_openai_api_call(
                operation=f"TTS Generation (Parallel) - Article {article_id}, chunk {chunk_idx}",
                request_data=tts_request_data,
                response_data=tts_response_data,
                duration_ms=tts_duration_ms,
            )

            # Extract token usage for stats
            tokens_used = 0
            if hasattr(response, "usage") and hasattr(response.usage, "total_tokens"):
                try:
                    tokens_used = int(response.usage.total_tokens)
                except (ValueError, TypeError):
                    tokens_used = 0
            elif hasattr(response, "headers"):
                header_value = response.headers.get("x-openai-tokens-used")
                if header_value is not None:
                    try:
                        tokens_used = int(header_value)
                    except (ValueError, TypeError):
                        tokens_used = 0

            # Save usage statistics
            try:
                from django.db import transaction

                from .models import OpenAIUsageStats

                user = article.feed.user
                word_count = len(chunk_text.split())

                with transaction.atomic():
                    OpenAIUsageStats.objects.create(
                        user=user,
                        article=article,
                        tokens_used=tokens_used,
                        processing_time_ms=tts_duration_ms,
                        word_count=word_count,
                    )
                    logger.debug(
                        f"Usage stats saved for article {article_id}, chunk {chunk_idx}"
                    )
            except Exception as stats_exc:
                logger.error(
                    f"Failed to save usage stats for chunk {chunk_idx}: {stats_exc}"
                )

        except Exception as tts_exc:
            tts_end_time = time.monotonic()
            tts_duration_ms = int((tts_end_time - tts_start_time) * 1000)

            # Log failed TTS API call
            from .utils import log_openai_api_call

            log_openai_api_call(
                operation=f"TTS Generation (Parallel) - Article {article_id}, chunk {chunk_idx}",
                request_data=tts_request_data,
                error=tts_exc,
                duration_ms=tts_duration_ms,
            )

            # Check if this is a retryable error
            error_str = str(tts_exc).lower()
            if any(
                term in error_str
                for term in ["rate limit", "quota", "timeout", "503", "502"]
            ):
                if self.request.retries < self.max_retries:
                    countdown = 60 * (2**self.request.retries)
                    logger.info(
                        f"Retrying chunk {chunk_idx} in {countdown}s due to: {tts_exc}"
                    )
                    raise self.retry(exc=tts_exc, countdown=countdown)

            raise tts_exc

        end_time = time.monotonic()
        total_duration_ms = int((end_time - start_time) * 1000)

        logger.info(
            f"TTS chunk {chunk_idx} completed successfully in {total_duration_ms}ms "
            f"for article {article_id}"
        )

        return (chunk_idx, str(temp_file_path), None)

    except Exception as e:
        end_time = time.monotonic()
        total_duration_ms = int((end_time - start_time) * 1000)

        error_msg = f"TTS chunk {chunk_idx} failed: {e}"
        logger.error(f"{error_msg} (duration: {total_duration_ms}ms)")
        logger.debug(traceback.format_exc())

        # Clean up temp file if it was created
        if temp_file_path and Path(temp_file_path).exists():
            try:
                os.remove(temp_file_path)
            except OSError as cleanup_exc:
                logger.error(
                    f"Failed to cleanup temp file {temp_file_path}: {cleanup_exc}"
                )

        return (chunk_idx, None, error_msg)


@shared_task(bind=True)
def stitch_audio_and_finalize(
    self,
    chunk_results: List[Tuple[int, Optional[str], Optional[str]]],
    article_id: int,
    final_audio_uuid: str,
) -> str:
    """
    Combine audio chunks and finalize article processing.

    Args:
        chunk_results: List of (chunk_idx, temp_file_path, error_message) tuples
        article_id: ID of the article being processed
        final_audio_uuid: UUID for the final audio file

    Returns:
        Success/failure message
    """
    start_time = time.monotonic()
    temp_files_to_cleanup = []

    try:
        # Get article
        try:
            article = Article.objects.get(id=article_id)
        except Article.DoesNotExist:
            error_msg = f"Article {article_id} not found for finalization"
            logger.error(error_msg)
            return error_msg

        # Validate article status
        if article.status != Article.PROCESSING:
            error_msg = (
                f"Article {article_id} no longer processing (status: {article.status})"
            )
            logger.warning(error_msg)
            return error_msg

        # Sort and analyze results
        chunk_results.sort(key=lambda x: x[0])  # Sort by chunk_idx
        successful_chunks = [(idx, path) for idx, path, error in chunk_results if path]
        failed_chunks = [(idx, error) for idx, path, error in chunk_results if not path]

        logger.info(
            f"Finalizing article {article_id}: {len(successful_chunks)} successful chunks, "
            f"{len(failed_chunks)} failed chunks"
        )

        # Check if we have enough successful chunks
        if not successful_chunks:
            error_msg = f"No successful TTS chunks for article {article_id}"
            logger.error(error_msg)

            article.status = Article.FAILED
            article.error_message = f"All TTS chunks failed. Errors: {failed_chunks}"
            article.save(update_fields=["status", "error_message"])

            return error_msg

        if len(failed_chunks) > len(successful_chunks):
            error_msg = f"Too many failed chunks ({len(failed_chunks)}/{len(chunk_results)}) for article {article_id}"
            logger.error(error_msg)

            article.status = Article.FAILED
            article.error_message = (
                f"Majority of chunks failed. Failed: {failed_chunks}"
            )
            article.save(update_fields=["status", "error_message"])

            return error_msg

        # Log warnings for failed chunks but continue
        if failed_chunks:
            logger.warning(
                f"Some chunks failed for article {article_id}: {failed_chunks}"
            )

        # Collect temp files for cleanup
        temp_files_to_cleanup = [path for _, path in successful_chunks]

        # Prepare final audio file path
        final_audio_path = Path(article.get_canonical_audio_path())
        final_audio_path.parent.mkdir(parents=True, exist_ok=True)

        # Prepare audio metadata
        feed_name = "My Podcast"
        if article.feed and article.feed.name:
            feed_name = article.feed.name

        tags_dict = {
            "title": article.title or "Untitled Article",
            "artist": feed_name,
            "album": feed_name,
        }
        export_parameters = ["-id3v2_version", "3", "-write_id3v1", "1"]

        # Stitch audio files
        if len(successful_chunks) == 1:
            # Single file - just copy with tags
            single_audio_path = successful_chunks[0][1]
            audio_segment = AudioSegment.from_mp3(single_audio_path)
            audio_segment = audio_segment.set_frame_rate(44100)
            audio_segment.export(
                str(final_audio_path),
                format="mp3",
                bitrate="128k",
                tags=tags_dict,
                parameters=export_parameters,
            )
            logger.info(f"Processed single audio file for article {article_id}")

        else:
            # Multiple files - combine them
            combined_audio = AudioSegment.empty()

            for chunk_idx, temp_file_path in successful_chunks:
                try:
                    segment_audio = AudioSegment.from_mp3(temp_file_path)
                    combined_audio += segment_audio
                    logger.debug(f"Added chunk {chunk_idx} to combined audio")
                except Exception as segment_exc:
                    logger.error(
                        f"Failed to process chunk {chunk_idx} ({temp_file_path}): {segment_exc}"
                    )
                    # Continue with other segments

            if combined_audio.duration_seconds > 0:
                combined_audio = combined_audio.set_frame_rate(44100)
                combined_audio.export(
                    str(final_audio_path),
                    format="mp3",
                    bitrate="128k",
                    tags=tags_dict,
                    parameters=export_parameters,
                )
                logger.info(
                    f"Combined {len(successful_chunks)} audio chunks for article {article_id}, "
                    f"duration: {combined_audio.duration_seconds:.1f}s"
                )
            else:
                raise ValueError("Combined audio has zero duration")

        # Update article status
        article.set_canonical_audio_path()
        article.status = Article.COMPLETED
        article.error_message = None

        # Include any warnings about failed chunks
        if failed_chunks:
            failed_chunk_indices = [idx for idx, _ in failed_chunks]
            failed_chunk_errors = [error for _, error in failed_chunks]
            warning_msg = f"Completed with {len(failed_chunks)} failed chunks: {failed_chunk_indices}"

            # Store detailed processing notes for user visibility
            article.processing_notes = (
                f"⚠️ Audio may be incomplete - {len(failed_chunks)} of {len(chunk_results)} chunks failed to process.\n"
                f"Missing chunk indices: {failed_chunk_indices}\n"
                f"Errors: {'; '.join(failed_chunk_errors[:3])}"  # Limit error details to prevent huge text
                + ("..." if len(failed_chunk_errors) > 3 else "")
            )

            logger.warning(f"Article {article_id}: {warning_msg}")
        else:
            article.processing_notes = None

        article.save(
            update_fields=[
                "audio_file_path",
                "status",
                "error_message",
                "processing_notes",
                "multi_voice_data",
                "voice_parameters",
                "detected_genre",
            ]
        )

        end_time = time.monotonic()
        total_duration_ms = int((end_time - start_time) * 1000)

        success_msg = (
            f"Article {article_id} finalized successfully in {total_duration_ms}ms"
        )
        logger.info(success_msg)

        return success_msg

    except Exception as e:
        end_time = time.monotonic()
        total_duration_ms = int((end_time - start_time) * 1000)

        error_msg = f"Failed to finalize article {article_id}: {e}"
        logger.error(f"{error_msg} (duration: {total_duration_ms}ms)")
        logger.debug(traceback.format_exc())

        # Update article with error
        try:
            article = Article.objects.get(id=article_id)
            article.status = Article.FAILED
            article.error_message = f"Finalization failed: {e}"
            article.save(update_fields=["status", "error_message"])
        except Exception as save_exc:
            logger.error(
                f"Failed to update article {article_id} with error: {save_exc}"
            )

        return error_msg

    finally:
        # Clean up temporary files
        for temp_file_path in temp_files_to_cleanup:
            if temp_file_path and Path(temp_file_path).exists():
                try:
                    os.remove(temp_file_path)
                    logger.debug(f"Cleaned up temp file: {temp_file_path}")
                except OSError as cleanup_exc:
                    logger.error(
                        f"Failed to cleanup temp file {temp_file_path}: {cleanup_exc}"
                    )
