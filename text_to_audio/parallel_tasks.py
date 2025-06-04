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

from django.conf import settings

import openai
from celery import shared_task
from pydub import AudioSegment

from .models import Article
from .rate_limiter import get_rate_limiter
from .tts_utils import _clamp_tts_speed, _configure_model_aware_speed

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    max_retries=2,
    default_retry_delay=30,
    soft_time_limit=150,
    time_limit=180,
)
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
        speed = _clamp_tts_speed(speed)

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

        # Prepare TTS request with model-aware speed handling
        tts_model = getattr(settings, "OPENAI_TTS_MODEL", "tts-1")
        tts_request_data = {
            "model": tts_model,
            "voice": voice_name,
            "input": chunk_text,
        }

        # Configure model-aware speed and instructions
        speed_updates, final_instructions = _configure_model_aware_speed(
            tts_model, speed, instructions or ""
        )

        # Apply speed configuration updates
        tts_request_data.update(speed_updates)

        # Add instructions parameter only for gpt-4o models (tts-1 models don't support instructions)
        if final_instructions and tts_model.startswith("gpt-4o"):
            tts_request_data["instructions"] = final_instructions

        # Log TTS API call details with model-aware speed handling
        speed_param = tts_request_data.get("speed", "via instructions")
        logger.info(
            f"TTS Chunk {chunk_idx} API Call - Article {article_id}: "
            f"model={tts_model}, voice={voice_name}, speed={speed_param}, "
            f"text_length={len(chunk_text)} chars"
            + (f", instructions='{final_instructions}'" if final_instructions else "")
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

        # Create ordered mapping of chunk indices to file paths
        # This ensures we process chunks in correct chronological order even with gaps
        successful_chunks_map = {idx: path for idx, path in successful_chunks}

        logger.info(
            f"Finalizing article {article_id}: {len(successful_chunks)} successful chunks, "
            f"{len(failed_chunks)} failed chunks"
        )

        # Check if we have enough successful chunks
        if not successful_chunks:
            error_msg = f"No successful TTS chunks for article {article_id}"
            logger.error(error_msg)

            # Use race-safe update for failure case
            from django.db import transaction

            with transaction.atomic():
                locked_article = Article.objects.select_for_update().get(id=article_id)
                locked_article.status = Article.FAILED
                locked_article.error_message = (
                    f"All TTS chunks failed. Errors: {failed_chunks}"
                )
                locked_article.save(update_fields=["status", "error_message"])

            return error_msg

        if len(failed_chunks) > len(successful_chunks):
            error_msg = f"Too many failed chunks ({len(failed_chunks)}/{len(chunk_results)}) for article {article_id}"
            logger.error(error_msg)

            # Use race-safe update for failure case
            from django.db import transaction

            with transaction.atomic():
                locked_article = Article.objects.select_for_update().get(id=article_id)
                locked_article.status = Article.FAILED
                locked_article.error_message = (
                    f"Majority of chunks failed. Failed: {failed_chunks}"
                )
                locked_article.save(update_fields=["status", "error_message"])

            return error_msg

        # Log warnings for failed chunks but continue
        if failed_chunks:
            logger.warning(
                f"Some chunks failed for article {article_id}: {failed_chunks}"
            )

        # Collect temp files for cleanup (from ordered mapping)
        temp_files_to_cleanup = list(successful_chunks_map.values())

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
            single_chunk_idx = list(successful_chunks_map.keys())[0]
            single_audio_path = successful_chunks_map[single_chunk_idx]
            logger.info(f"Processing single audio file from chunk {single_chunk_idx}")
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
            # Multiple files - combine them in correct chronological order
            combined_audio = AudioSegment.empty()

            # Process chunks in sorted order by original index
            for chunk_idx in sorted(successful_chunks_map.keys()):
                temp_file_path = successful_chunks_map[chunk_idx]
                try:
                    segment_audio = AudioSegment.from_mp3(temp_file_path)
                    combined_audio += segment_audio
                    logger.debug(
                        f"Added chunk {chunk_idx} to combined audio (chronological order)"
                    )
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

        # Update article status with race-safe locking
        from django.db import transaction

        with transaction.atomic():
            # Use select_for_update to prevent race conditions on processing_notes
            locked_article = Article.objects.select_for_update().get(id=article_id)

            # Update article fields
            locked_article.set_canonical_audio_path()
            locked_article.status = Article.COMPLETED
            locked_article.error_message = None

            # Include any warnings about failed chunks
            if failed_chunks:
                failed_chunk_indices = [idx for idx, _ in failed_chunks]
                failed_chunk_errors = [error for _, error in failed_chunks]
                warning_msg = f"Completed with {len(failed_chunks)} failed chunks: {failed_chunk_indices}"

                # Store detailed processing notes for user visibility
                locked_article.processing_notes = (
                    f"⚠️ Audio may be incomplete - {len(failed_chunks)} of {len(chunk_results)} chunks failed to process.\n"
                    f"Missing chunk indices: {failed_chunk_indices}\n"
                    f"Errors: {'; '.join(failed_chunk_errors[:3])}"  # Limit error details to prevent huge text
                    + ("..." if len(failed_chunk_errors) > 3 else "")
                )

                logger.warning(f"Article {article_id}: {warning_msg}")
            else:
                locked_article.processing_notes = None

            locked_article.save(
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

        # Update article with error using race-safe locking
        try:
            from django.db import transaction

            with transaction.atomic():
                locked_article = Article.objects.select_for_update().get(id=article_id)
                locked_article.status = Article.FAILED
                locked_article.error_message = f"Finalization failed: {e}"
                locked_article.save(update_fields=["status", "error_message"])
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


@shared_task(bind=True, queue="audio_processing")
def process_large_article_batched(
    self,
    chunk_task_signatures: list,
    article_id: int,
    final_audio_uuid: str,
    max_concurrent: int,
) -> str:
    """
    Process large articles with batch coordination on audio_processing queue.

    This task runs on the audio_processing queue (not article_processing)
    to avoid blocking the main article processing worker pool.

    Args:
        chunk_task_signatures: Serialized chunk task signatures
        article_id: ID of the article being processed
        final_audio_uuid: UUID for the final audio file
        max_concurrent: Maximum chunks to process per batch

    Returns:
        Success/failure message
    """
    from django.conf import settings

    from celery import group

    try:
        logger.info(
            f"Starting batched processing for article {article_id}: "
            f"{len(chunk_task_signatures)} total chunks, max_concurrent={max_concurrent}"
        )

        all_results = []

        # Process chunks in batches
        for i in range(0, len(chunk_task_signatures), max_concurrent):
            batch = chunk_task_signatures[i : i + max_concurrent]
            batch_num = (i // max_concurrent) + 1

            logger.info(
                f"Processing batch {batch_num} for article {article_id}: "
                f"{len(batch)} chunks"
            )

            # Create group for this batch
            batch_group = group(batch)
            batch_result = batch_group.apply_async()

            try:
                batch_chunk_results = batch_result.get(
                    timeout=getattr(settings, "PARALLEL_TTS_CHORD_TIMEOUT", 3600)
                )
                all_results.extend(batch_chunk_results)

                logger.info(
                    f"Batch {batch_num} completed for article {article_id}: "
                    f"{len(batch_chunk_results)} results"
                )

            except Exception as batch_exc:
                logger.error(
                    f"Batch {batch_num} failed for article {article_id}: {batch_exc}"
                )

                # If we have no results at all, fail completely
                if not all_results:
                    raise batch_exc

                # Otherwise, try to continue with partial results
                logger.warning(
                    f"Continuing with {len(all_results)} results from previous batches"
                )
                break

        # Finalize with all accumulated results
        if all_results:
            logger.info(
                f"Finalizing article {article_id} with {len(all_results)} chunks"
            )

            try:
                finalize_result = stitch_audio_and_finalize.apply_async(
                    args=[all_results, article_id, final_audio_uuid],
                    queue="audio_processing",
                ).get(timeout=getattr(settings, "PARALLEL_TTS_FINALIZE_TIMEOUT", 300))

                return finalize_result
            except Exception as finalize_exc:
                logger.error(
                    f"Finalization failed for article {article_id}: {finalize_exc}"
                )

                # Ensure article is marked as failed immediately
                try:
                    from django.db import transaction

                    from .models import Article

                    with transaction.atomic():
                        locked_article = Article.objects.select_for_update().get(
                            id=article_id
                        )
                        locked_article.status = Article.FAILED
                        locked_article.error_message = (
                            f"Audio finalization failed: {finalize_exc}"
                        )
                        locked_article.save(update_fields=["status", "error_message"])
                        logger.info(
                            f"Article {article_id} marked as FAILED due to finalization failure"
                        )
                except Exception as save_exc:
                    logger.error(
                        f"Failed to mark article {article_id} as failed after finalization error: {save_exc}"
                    )

                # Re-raise the exception to ensure Celery sees this as a task failure
                raise finalize_exc
        else:
            raise ValueError("No successful chunks to process")

    except Exception as e:
        logger.error(f"Batched processing failed for article {article_id}: {e}")

        # Mark article as failed using race-safe locking
        try:
            from django.db import transaction

            from .models import Article

            with transaction.atomic():
                locked_article = Article.objects.select_for_update().get(id=article_id)
                locked_article.status = Article.FAILED
                locked_article.error_message = f"Batched processing failed: {e}"
                locked_article.save(update_fields=["status", "error_message"])
        except Exception as save_exc:
            logger.error(
                f"Failed to update article {article_id} with error: {save_exc}"
            )

        return f"Failed to process article {article_id}: {e}"
