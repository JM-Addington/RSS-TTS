"""Celery tasks for processing articles."""

# flake8: noqa: E501

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
from .services.chunk_tone_service import ChunkToneService
from .services.content_analysis import MAX_ANALYSIS_WORDS, ContentAnalysisService
from .services.voice_configuration import VoiceConfigurationService
from .services.voice_parameter_generation import VoiceParameterGenerationService
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


def _legacy_chunk_text(text: str, max_length: int = 4000) -> tuple[bool, list[str]]:
    """Split text into chunks for TTS processing (optimized for large texts).

    Uses a linear scanning approach for better performance on large documents.
    Prioritizes natural breaks in this order:
    1. Line breaks (\n)
    2. Sentence boundaries (. ! ?)
    3. Clause boundaries (; ,)
    4. Word boundaries (spaces)
    5. Force splits within words as last resort

    Returns:
        tuple: (success, chunks)
            - success (bool): True if all splits were at natural boundaries
            - chunks (list): List of text chunks, each <= max_length
    """
    logger.debug(
        f"_chunk_text called with text of len {len(text)} and max_length {max_length}"
    )

    if not text:
        return True, []

    if len(text) <= max_length:
        return True, [text]

    chunks = []
    perfect_split = True
    current_chunk = ""

    # Define break characters in priority order
    sentence_breaks = {".", "!", "?"}
    clause_breaks = {";", ","}

    i = 0
    text_len = len(text)

    while i < text_len:
        char = text[i]

        # Check if adding this character would exceed max_length
        if len(current_chunk) + 1 > max_length:
            # We need to break here, find the best break point in current_chunk
            if current_chunk:
                break_point = _legacy_find_best_break_point(current_chunk, max_length)
                if break_point > 0:
                    chunks.append(current_chunk[:break_point].strip())
                    current_chunk = current_chunk[break_point:].strip()
                    if current_chunk and len(current_chunk) > max_length:
                        # Still too long, force split
                        perfect_split = False
                        chunks.append(current_chunk[:max_length])
                        current_chunk = current_chunk[max_length:]
                else:
                    # No good break point found, force split
                    perfect_split = False
                    chunks.append(current_chunk[:max_length])
                    current_chunk = current_chunk[max_length:]
            # Check if we can now add the current character after splitting
            if len(current_chunk) + 1 <= max_length:
                # We can now add the character, fall through to normal processing
                pass
            else:
                # Still can't add the character, skip it and move to next
                # This prevents the infinite loop by ensuring i is incremented
                i += 1
                continue

        # Add character to current chunk
        current_chunk += char

        # Check for natural break opportunities
        if char == "\n":
            # Line break - highest priority
            chunks.append(current_chunk.strip())
            current_chunk = ""
        elif char in sentence_breaks and i + 1 < text_len and text[i + 1].isspace():
            # Sentence break followed by space
            current_chunk += text[i + 1]  # Include the space
            chunks.append(current_chunk.strip())
            current_chunk = ""
            i += 1  # Skip the space we just added

        i += 1

    # Add any remaining chunk
    if current_chunk.strip():
        if len(current_chunk) > max_length:
            # Need to split the remaining chunk
            remaining = current_chunk.strip()
            while remaining:
                if len(remaining) <= max_length:
                    chunks.append(remaining)
                    break

                break_point = _legacy_find_best_break_point(remaining, max_length)
                if break_point > 0:
                    chunks.append(remaining[:break_point].strip())
                    remaining = remaining[break_point:].strip()
                else:
                    # Force split
                    perfect_split = False
                    chunks.append(remaining[:max_length])
                    remaining = remaining[max_length:]
        else:
            chunks.append(current_chunk.strip())

    # Filter out empty chunks
    chunks = [chunk for chunk in chunks if chunk]

    return perfect_split, chunks


def _legacy_find_best_break_point(text: str, max_length: int) -> int:
    """Find the best break point within a text segment.

    Returns the index where to break, or 0 if no good break point found.
    """
    if len(text) <= max_length:
        return len(text)

    # Search backwards from max_length for break opportunities
    search_text = text[:max_length]

    # Priority 1: Sentence breaks with space after
    for i in range(len(search_text) - 2, -1, -1):
        if search_text[i] in {".", "!", "?"} and search_text[i + 1].isspace():
            return i + 2  # Include the punctuation and space

    # Priority 2: Clause breaks with space after
    for i in range(len(search_text) - 2, -1, -1):
        if search_text[i] in {";", ","} and search_text[i + 1].isspace():
            return i + 2

    # Priority 3: Word boundaries (spaces)
    for i in range(len(search_text) - 1, -1, -1):
        if search_text[i].isspace():
            return i + 1

    # No good break point found
    return 0


def _generate_title(client, text: str) -> str:
    """Generate a short title for the article using GPT."""
    from django.conf import settings

    try:
        response = client.chat.completions.create(
            model=getattr(settings, "OPENAI_TITLE_MODEL", "gpt-4o-mini"),
            messages=[
                {
                    "role": "user",
                    "content": (
                        "Provide a concise title for this article:\n\n" + text[:5000]
                    ),
                }
            ],
            max_tokens=10,
            temperature=0.5,
        )
        title = response.choices[0].message.content.strip()
        return str(title)
    except Exception as e:  # pragma: no cover - safeguard
        logger.error(f"Failed to generate title: {e}")
        return "Untitled Article"  # type: ignore[return-value]


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
    # Holds all generated audio pieces for final stitching
    generated_audio_files: list[Path] = []
    final_audio_path: Path | None = None

    # Initialize OpenAI client and user once
    client = openai.OpenAI(api_key=settings.OPENAI_API_KEY)
    user = article.feed.user  # For _save_openai_usage_stats

    try:
        # Ensure canonical media directory exists
        media_root = Path(settings.MEDIA_ROOT)
        article.ensure_canonical_directory_exists()

        # Use canonical directory for temporary files during processing
        articles_dir = media_root / "articles"
        article_media_dir = articles_dir  # For temporary files during processing

        # Generate a UUID for the article audio file if not already set
        if not article.audio_uuid:
            article.audio_uuid = uuid.uuid4()
            # Save immediately if other parts rely on it
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

        if not article.text_content:  # This check is crucial
            logger.error(
                f"Article {article_id} has no text_content after potential URL fetch."
            )
            raise ValueError("Article text_content is empty.")

        if not article.title:
            logger.info(f"Generating title for Article ID: {article_id}")
            article.title = _generate_title(client, article.text_content)
            article.save(update_fields=["title"])

        # Analyze content to get multi-voice data first to avoid duplicate LLM calls.
        # This is done before voice configuration and TTS generation.
        # The result will be stored in article.multi_voice_data and can be reused by voice parameter generation.
        # If this step fails or if the data is invalid, we will fall back to single-voice generation.
        if article.text_content:  # Only proceed if there's text content
            try:
                logger.info(
                    f"Performing content analysis for Article ID: {article_id} to get multi-voice data."
                )
                content_service = ContentAnalysisService()

                # Use the entire article text for analysis, truncated to MAX_ANALYSIS_WORDS words
                analysis_text_sample = " ".join(
                    article.text_content.split()[:MAX_ANALYSIS_WORDS]
                )

                analysis_result_json = content_service.analyze_content(
                    analysis_text_sample, title=article.title
                )

                # Validate that we got actual JSON-serializable data, not a mock
                if analysis_result_json is not None and not hasattr(
                    analysis_result_json, "_mock_name"
                ):
                    article.multi_voice_data = analysis_result_json
                else:
                    article.multi_voice_data = None
                # The fields article.summary, article.detected_tone, article.voice_id, article.speed
                # are no longer directly set from this specific analysis call.
                # They might be deprecated or populated via a different mechanism if still needed.
                # For instance, a summary might be part of analysis_result_json or a separate LLM call.
                # article.voice_id and article.speed are now primarily for fallback.
                article.save(update_fields=["multi_voice_data"])
                logger.info(
                    f"Content analysis successful, multi_voice_data updated for Article ID: {article_id}"
                )

            except Exception as analysis_exc:
                logger.error(
                    f"Content analysis failed for Article ID {article_id}: {analysis_exc}"
                )
                logger.debug(traceback.format_exc())
                article.multi_voice_data = None  # Ensure it's None on failure
                article.save(update_fields=["multi_voice_data"])
                # Do not re-raise here; allow fallback to single voice processing later.
        else:
            logger.warning(
                f"Article ID: {article_id} has no text_content. Skipping content analysis."
            )
            article.multi_voice_data = None
            # No need to save here if it was already None or if text_content was missing from start

        # Configure article voice based on feed preferences (auto-voice if enabled)
        # This now happens after content analysis so voice parameter generation can reuse analysis results
        try:
            logger.info(f"Configuring voice settings for Article ID: {article_id}")
            voice_config_service = VoiceConfigurationService()
            voice_config_service.configure_article_voice(article)
            logger.info(f"Voice configuration complete for Article ID: {article_id}")
        except Exception as voice_config_exc:
            logger.error(
                f"Voice configuration failed for Article ID {article_id}: {voice_config_exc}"
            )
            logger.debug(traceback.format_exc())
            # Continue with existing voice settings as fallback

        # --- ChunkTone LLM Service (New) or Multi-Voice TTS Generation (Legacy) ---
        chunk_tone_generation_successful = False
        if settings.ENABLE_CHUNK_TONE_LLM:
            try:
                logger.info(f"Using ChunkToneService for Article ID: {article_id}")
                chunk_tone_service = ChunkToneService()

                # Prepare text for chunking (include title)
                text_for_chunking = article.text_content
                if article.title:
                    text_for_chunking = f"{article.title}.\n\n{article.text_content}"

                # Get chunks from LLM service
                chunk_tone_payload = chunk_tone_service.get_payload(
                    text=text_for_chunking,
                    title=article.title or "Untitled",
                    max_chars=4000,
                )

                logger.info(
                    f"ChunkToneService returned {len(chunk_tone_payload.chunks)} chunks for Article ID: {article_id}"
                )

                # Resolve speed using the same logic as single-voice fallback
                if article.voice_parameters:
                    resolved_speed = (
                        article.voice_parameters.get("speed") or article.speed or 1.0
                    )
                else:
                    resolved_speed = article.speed or 1.0

                # Process each chunk with TTS
                for chunk_idx, chunk_data in enumerate(chunk_tone_payload.chunks):
                    chunk_temp_file_path = (
                        article_media_dir
                        / f"temp_article_{article.audio_uuid}_chunk_{chunk_idx}_{uuid.uuid4()}.mp3"
                    )
                    start_time = time.monotonic()

                    # Generate voice prompt for chunk tone
                    chunk_voice_prompt = "Speak in a clear, engaging manner with appropriate expression for the content."

                    response = client.audio.speech.create(
                        model=getattr(settings, "OPENAI_TTS_MODEL", "tts-1"),
                        voice=chunk_data.voice.voice,
                        input=chunk_data.text,
                        speed=resolved_speed,
                        instructions=chunk_voice_prompt,
                    )
                    response.stream_to_file(chunk_temp_file_path)
                    end_time = time.monotonic()
                    processing_time_ms = int((end_time - start_time) * 1000)

                    tokens_used = 0
                    if hasattr(response, "usage") and hasattr(
                        response.usage, "total_tokens"
                    ):
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

                    generated_audio_files.append(chunk_temp_file_path)
                    word_count = len(chunk_data.text.split())
                    _save_openai_usage_stats(
                        user=user,
                        article=article,
                        article_id=article_id,
                        chunk_index=f"chunk_tone_{chunk_idx}",
                        tokens_used=tokens_used,
                        processing_time_ms=processing_time_ms,
                        word_count=word_count,
                    )

                if generated_audio_files:
                    chunk_tone_generation_successful = True
                    logger.info(
                        f"ChunkToneService generation successful for Article ID: {article_id}, {len(generated_audio_files)} audio pieces generated."
                    )
                else:
                    logger.warning(
                        f"ChunkToneService attempted for Article ID {article_id}, but no audio files were generated."
                    )

            except Exception as ct_exc:
                logger.error(
                    f"ChunkToneService generation failed for Article ID {article_id}: {ct_exc}"
                )
                logger.debug(traceback.format_exc())
                # Clean up any partially generated files before fallback
                for temp_file in generated_audio_files:
                    if temp_file.exists():
                        os.remove(temp_file)
                generated_audio_files = []
                chunk_tone_generation_successful = False

        # --- Legacy Multi-Voice TTS Generation Attempt ---
        multi_voice_generation_successful = False
        if not chunk_tone_generation_successful and _is_valid_multi_voice_data(
            article.multi_voice_data
        ):
            try:
                logger.info(
                    f"Attempting multi-voice TTS generation for Article ID: {article_id}"
                )
                voices_map = {v["name"]: v for v in article.multi_voice_data["voices"]}

                concatenated_multi_voice_text = ""
                for segment_idx, segment_data in enumerate(
                    article.multi_voice_data["audio_segments"]
                ):
                    segment_text = segment_data.get("text")
                    voice_name = segment_data.get("voice_name")

                    if not segment_text or not voice_name:
                        logger.warning(
                            f"Invalid segment data (segment {segment_idx}) in Article {article_id}: {segment_data}. Skipping."
                        )
                        continue

                    concatenated_multi_voice_text += (
                        segment_text  # For later validation
                    )

                    voice_definition = voices_map.get(voice_name)
                    if not voice_definition:
                        logger.error(
                            f"Voice '{voice_name}' not defined in multi_voice_data for Article {article_id}, segment {segment_idx}."
                        )
                        # Triggers fallback
                        raise ValueError(f"Voice '{voice_name}' not defined.")

                    # Ensure tts_model is actually the OpenAI voice name like "alloy", "echo"
                    # The prompt asks for "tts_model": "string (e.g., 'alloy', 'onyx')"
                    # The API client.audio.speech.create takes `voice` parameter for this.
                    tts_api_voice = voice_definition.get("tts_model")
                    if not tts_api_voice:
                        logger.error(
                            f"Missing 'tts_model' for voice '{voice_name}' in Article {article_id}."
                        )
                        raise ValueError(
                            f"Missing 'tts_model' for voice '{voice_name}'."
                        )

                    tts_speed = float(voice_definition.get("tts_speed", 1.0))
                    # Basic validation for speed to prevent API errors
                    if not (0.25 <= tts_speed <= 4.0):
                        logger.warning(
                            f"Invalid TTS speed {tts_speed} for voice {voice_name}. Clamping to range [0.25, 4.0]."
                        )
                        tts_speed = max(0.25, min(tts_speed, 4.0))

                    # Chunk the segment's text if necessary
                    _, segment_text_chunks = _legacy_chunk_text(segment_text)
                    if not segment_text_chunks:
                        logger.warning(
                            f"Segment {segment_idx} for article {article_id} ('{voice_name}') resulted in no text chunks. Skipping."
                        )
                        continue

                    logger.info(
                        f"Processing segment {segment_idx+1}/{len(article.multi_voice_data['audio_segments'])} ('{voice_name}', {len(segment_text_chunks)} sub-chunks) for Article ID: {article_id}"
                    )

                    for chunk_idx, chunk_text in enumerate(segment_text_chunks):
                        chunk_temp_file_path = (
                            article_media_dir
                            / f"temp_article_{article.audio_uuid}_segment_{segment_idx}_chunk_{chunk_idx}_{uuid.uuid4()}.mp3"
                        )
                        start_time = time.monotonic()

                        # Generate voice prompt for multi-voice segment
                        voice_tone = voice_definition.get("tone", "neutral")
                        segment_voice_prompt = f"Use a {voice_tone} tone. Speak in a clear, engaging manner."

                        response = client.audio.speech.create(
                            model=getattr(
                                settings, "OPENAI_TTS_MODEL", "tts-1"
                            ),  # tts-1 or tts-1-hd
                            voice=tts_api_voice,  # This is 'alloy', 'echo', etc.
                            input=chunk_text,
                            speed=tts_speed,
                            instructions=segment_voice_prompt,
                        )
                        response.stream_to_file(chunk_temp_file_path)
                        end_time = time.monotonic()
                        processing_time_ms = int((end_time - start_time) * 1000)

                        tokens_used = 0
                        if hasattr(response, "usage") and hasattr(
                            response.usage, "total_tokens"
                        ):
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

                        generated_audio_files.append(chunk_temp_file_path)
                        word_count = len(chunk_text.split())
                        _save_openai_usage_stats(
                            user=user,
                            article=article,
                            article_id=article_id,
                            chunk_index=f"segment_{segment_idx}_chunk_{chunk_idx}",
                            tokens_used=tokens_used,
                            processing_time_ms=processing_time_ms,
                            word_count=word_count,
                        )

                # Validate concatenated text matches original (if possible, or a large portion of it)
                # This is a basic sanity check for the LLM's segmentation.
                # The LLM prompt for ContentAnalysisService asks for this:
                # "Ensure that the concatenation of all `text` fields in `audio_segments` exactly matches the original input text."
                # However, we use a sample for analysis (first 2000 chars). So we can only validate against that sample.
                text_sample_for_validation = (
                    article.text_content[:2000]
                    if len(article.text_content) > 2000
                    else article.text_content
                )
                # Allow some minor diff at end
                if not concatenated_multi_voice_text.startswith(
                    text_sample_for_validation.strip()[
                        : len(concatenated_multi_voice_text) - 50
                    ]
                ):
                    logger.warning(
                        f"Article {article_id}: Concatenated multi-voice text does not closely match the beginning of the original text sample. This might indicate an issue with segmentation from the LLM."
                    )
                    # Not raising an error here, but logging it. The audio will still be generated.

                if (
                    not generated_audio_files
                ):  # Check if any audio files were actually created
                    logger.warning(
                        f"Multi-voice processing attempted for Article ID {article_id}, but no audio files were generated."
                    )
                    # This will naturally lead to fallback if multi_voice_generation_successful remains False
                else:
                    multi_voice_generation_successful = True
                    logger.info(
                        f"Multi-voice TTS generation successful for Article ID: {article_id}, {len(generated_audio_files)} audio pieces generated."
                    )

            except Exception as mv_exc:
                logger.error(
                    f"Multi-voice TTS generation failed for Article ID {article_id}: {mv_exc}"
                )
                logger.debug(traceback.format_exc())
                # Clean up any partially generated multi-voice files before fallback
                for temp_file in generated_audio_files:
                    if temp_file.exists():
                        os.remove(temp_file)
                generated_audio_files = []  # Reset for fallback
                multi_voice_generation_successful = (
                    False  # Ensure fallback is triggered
                )
        else:
            logger.info(
                f"Skipping multi-voice generation for Article ID: {article_id} due to missing or invalid multi_voice_data."
            )

        # --- Fallback to Single-Voice Generation ---
        if (
            not chunk_tone_generation_successful
            and not multi_voice_generation_successful
        ):
            logger.info(
                f"Falling back to single-voice TTS generation for Article ID: {article_id}"
            )

            # Ensure any previous (failed multi-voice) temp files are cleared
            if (
                generated_audio_files
            ):  # Should be empty if mv_exc occurred and was handled
                logger.warning(
                    f"Clearing {len(generated_audio_files)} residual files before fallback."
                )
                for temp_file in generated_audio_files:
                    if temp_file.exists():
                        os.remove(temp_file)
                generated_audio_files = []

            text_for_audio = article.text_content
            if article.title:
                text_for_audio = f"{article.title}.\n\n{article.text_content}"

            _, text_chunks = _legacy_chunk_text(text_for_audio)
            if not text_chunks:
                raise ValueError(
                    "No text chunks generated from text_content for single-voice fallback."
                )

            logger.info(
                f"Generated {len(text_chunks)} chunks for single-voice fallback (Article ID: {article_id})"
            )

            # Use enhanced voice parameters if available (from auto-voice)
            voice_prompt = None
            if article.voice_parameters:
                # Check voice field first, then voice_id, then voice_parameters, then default
                fallback_voice = (
                    article.voice
                    or article.voice_parameters.get("voice_id")
                    or article.voice_id
                    or getattr(settings, "OPENAI_TTS_VOICE", "alloy")
                )
                fallback_speed = (
                    article.voice_parameters.get("speed") or article.speed or 1.0
                )

                # Generate enhanced prompt if available
                parameter_service = VoiceParameterGenerationService()
                voice_prompt = parameter_service.generate_enhanced_prompt(
                    article.voice_parameters
                )
            else:
                # Check voice field first, then voice_id, then default
                fallback_voice = (
                    article.voice
                    or article.voice_id
                    or getattr(settings, "OPENAI_TTS_VOICE", "alloy")
                )
                fallback_speed = article.speed or 1.0

            # Note: article.voice_id and article.speed might not be populated if the primary analysis
            # path only sets multi_voice_data. These fields should ideally be populated by user preferences
            # or a simpler, separate analysis if multi-voice fails or is not applicable.
            # For now, this relies on them being potentially set or using global defaults.
            logger.info(
                f"Fallback voice: {fallback_voice}, speed: {fallback_speed} for Article ID: {article_id}"
            )

            for i, chunk in enumerate(text_chunks):
                temp_file_path = (
                    article_media_dir
                    / f"temp_article_{article.audio_uuid}_fallback_chunk_{i}_{uuid.uuid4()}.mp3"
                )
                start_time = time.monotonic()

                # Create TTS request
                tts_args = {
                    "model": getattr(settings, "OPENAI_TTS_MODEL", "tts-1"),
                    "voice": fallback_voice,
                    "input": chunk,
                    "speed": fallback_speed,
                }

                # Add voice prompt instructions if available
                if voice_prompt:
                    tts_args["instructions"] = voice_prompt

                response = client.audio.speech.create(**tts_args)
                response.stream_to_file(temp_file_path)
                end_time = time.monotonic()
                processing_time_ms = int((end_time - start_time) * 1000)

                tokens_used = 0
                if hasattr(response, "usage") and hasattr(
                    response.usage, "total_tokens"
                ):
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

                generated_audio_files.append(temp_file_path)
                word_count = len(chunk.split())
                _save_openai_usage_stats(
                    user=user,
                    article=article,
                    article_id=article_id,
                    chunk_index=f"fallback_chunk_{i}",
                    tokens_used=tokens_used,
                    processing_time_ms=processing_time_ms,
                    word_count=word_count,
                )

            if (
                not generated_audio_files
            ):  # Should not happen if text_chunks is not empty
                raise ValueError(
                    "Single-voice fallback processing attempted but no audio files were generated."
                )
            logger.info(
                f"Single-voice fallback TTS generation successful for Article ID: {article_id}, {len(generated_audio_files)} audio pieces generated."
            )

        # --- Audio Stitching and Finalization (Common for both paths) ---
        if not generated_audio_files:
            raise ValueError(
                "No audio files were generated by any TTS process. Cannot proceed."
            )

        # Use canonical path for final audio file
        final_audio_path = Path(article.get_canonical_audio_path())

        feed_name = "My Podcast"  # Default
        if article.feed and article.feed.name:
            feed_name = article.feed.name

        tags_dict = {
            "title": article.title or "Untitled Article",
            "artist": feed_name,
            "album": feed_name,
        }
        export_parameters = ["-id3v2_version", "3", "-write_id3v1", "1"]

        if len(generated_audio_files) == 1:
            single_audio_path = generated_audio_files[0]
            # It's safer to copy/process the file rather than renaming, then clean up.
            # For single files, we still re-export to apply tags and ensure format.
            audio_segment = AudioSegment.from_mp3(single_audio_path)
            audio_segment = audio_segment.set_frame_rate(
                44100
            )  # Ensure consistent frame rate
            audio_segment.export(
                str(final_audio_path),
                format="mp3",
                bitrate="128k",
                tags=tags_dict,
                parameters=export_parameters,
            )
            logger.info(
                f"Processed single audio file and exported to {final_audio_path}"
            )
        else:
            combined_audio = AudioSegment.empty()
            for temp_file_path_item in generated_audio_files:
                try:
                    segment_audio = AudioSegment.from_mp3(temp_file_path_item)
                    combined_audio += segment_audio
                except Exception as e:  # Catch specific pydub errors if known
                    logger.error(
                        f"Pydub error processing chunk {temp_file_path_item} for article {article_id}: {e}"
                    )
                    # Decide if this should raise immediately or try to continue with other segments
                    raise ValueError(
                        f"Failed to process audio chunk {temp_file_path_item.name}: {e}"
                    ) from e

            if combined_audio.duration_seconds > 0:
                combined_audio = combined_audio.set_frame_rate(
                    44100
                )  # Ensure consistent frame rate
                combined_audio.export(
                    str(final_audio_path),
                    format="mp3",
                    bitrate="128k",
                    tags=tags_dict,
                    parameters=export_parameters,
                )
                logger.info(
                    f"Combined {len(generated_audio_files)} audio files and exported to {final_audio_path}"
                )
            else:
                # This case should ideally be prevented by checks earlier (e.g., if generated_audio_files is empty)
                raise ValueError(
                    "Combined audio is empty or has zero duration, cannot export."
                )

        # Set canonical audio path in database
        article.set_canonical_audio_path()
        article.status = Article.COMPLETED
        article.error_message = None  # Clear any previous error
        # Save multi_voice_data, voice_parameters, and other details
        article.save(
            update_fields=[
                "audio_file_path",
                "status",
                "error_message",
                "multi_voice_data",
                "voice_parameters",
                "detected_genre",
            ]
        )
        logger.info(
            f"Successfully processed Article ID: {article_id}. Audio at: {article.audio_file_path}"
        )
        return f"Article {article_id} processed successfully."

    except Exception as e:
        logger.error(f"Unhandled error processing Article ID {article_id}: {e}")
        detailed_error = traceback.format_exc()
        logger.error(detailed_error)

        article.status = Article.FAILED
        article.error_message = f"{type(e).__name__}: {e}\n{detailed_error[:1000]}"
        # Persist multi_voice_data even on failure, as it might be useful for debugging
        article.save(
            update_fields=[
                "status",
                "error_message",
                "multi_voice_data",
                "voice_parameters",
            ]
        )

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
                    logger.error(
                        f"Error deleting temporary file {temp_file_path_item}: {e}"
                    )


def _is_valid_multi_voice_data(data: dict | None) -> bool:
    """Validate the basic structure of multi_voice_data."""
    if not isinstance(data, dict):
        logger.debug("multi_voice_data is not a dict or is None.")
        return False
    if "voices" not in data or "audio_segments" not in data:
        logger.debug("multi_voice_data missing 'voices' or 'audio_segments' keys.")
        return False
    if not isinstance(data["voices"], list) or not isinstance(
        data["audio_segments"], list
    ):
        logger.debug("'voices' or 'audio_segments' is not a list.")
        return False
    if not data["voices"]:  # Must have at least one voice defined
        logger.debug("'voices' list is empty.")
        return False
    if not data["audio_segments"]:  # Must have at least one segment
        logger.debug("'audio_segments' list is empty.")
        return False

    # Check structure of first voice definition (sample check)
    first_voice = data["voices"][0]
    if not all(k in first_voice for k in ["name", "tone", "tts_model", "tts_speed"]):
        logger.debug(
            "First voice definition in 'voices' list is missing required keys."
        )
        return False

    # Check structure of first audio segment (sample check)
    first_segment = data["audio_segments"][0]
    if not all(k in first_segment for k in ["text", "voice_name"]):
        logger.debug(
            "First audio segment in 'audio_segments' list is missing required keys."
        )
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
