"""Celery tasks for processing articles."""

from __future__ import annotations

import logging
import os
import traceback
import uuid
from pathlib import Path

import openai
from celery import shared_task  # type: ignore
from django.conf import settings
from pydub import AudioSegment

from .models import Article

# Configure logging
logger = logging.getLogger(__name__)


def _chunk_text(text: str, max_length: int = 4000) -> tuple[bool, list[str]]:
    """Splits text into chunks for TTS processing.
    
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
    logger.debug(f"_chunk_text called with text of len {len(text)} and max_length {max_length}")
    
    if not text:
        return True, []
    
    # Check if the entire text fits within max_length
    if len(text) <= max_length:
        return True, [text]
    
    chunks = []
    perfect_split = True  # Track if we had to force-split any words
    
    # First split by line breaks
    lines = text.split('\n')
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
                if i < len(line) - 1 and line[i] in ['.', '!', '?'] and line[i+1].isspace():
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
                    semi_parts = sentence.split(';')
                    
                    for part in semi_parts:
                        part = part.strip()
                        if len(part) <= max_length:
                            clauses.append(part)
                        else:
                            # Split by commas
                            comma_parts = part.split(',')
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
                                # If adding this word exceeds max_length, store current chunk and start new one
                                if len(current_chunk) + len(word) + 1 > max_length:
                                    if current_chunk:
                                        clause_chunks.append(current_chunk)
                                    
                                    # If single word is longer than max_length, must force-split it
                                    if len(word) > max_length:
                                        perfect_split = False
                                        # Split the word into chunks of max_length
                                        for i in range(0, len(word), max_length):
                                            clause_chunks.append(word[i:i+max_length])
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
    """
    Process an article's text_content to generate an MP3 audio file.
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
        article_media_dir = media_root / "articles" / str(article.feed.user_id) / str(article.feed.id)
        article_media_dir.mkdir(parents=True, exist_ok=True)

        if not article.text_content:
            raise ValueError("Article text_content is empty.")

        # Get text chunks with default max_length of 4000
        success, text_chunks = _chunk_text(article.text_content)
        if not text_chunks:
            raise ValueError("No text chunks generated from text_content.")
        
        if not success:
            logger.warning(f"Article ID {article_id} required compromise splitting (some words forced to split)")
            
        logger.info(f"Generated {len(text_chunks)} chunks for Article ID: {article_id}")

        client = openai.OpenAI(api_key=settings.OPENAI_API_KEY)

        for i, chunk in enumerate(text_chunks):
            logger.debug(f"Processing chunk {i+1}/{len(text_chunks)} for Article ID: {article_id}")
            temp_file_path = article_media_dir / f"temp_article_{article_id}_chunk_{i}_{uuid.uuid4()}.mp3"
            
            try:
                response = client.audio.speech.create(
                    model=getattr(settings, "OPENAI_TTS_MODEL", "tts-1"),
                    voice=getattr(settings, "OPENAI_TTS_VOICE", "alloy"),
                    input=chunk,
                )
                response.stream_to_file(temp_file_path)
                temp_audio_files.append(temp_file_path)
                logger.debug(f"Saved audio chunk to {temp_file_path}")
            except openai.APIError as e:
                logger.error(f"OpenAI API error on chunk {i+1} for article {article_id}: {e}")
                # Decide if retry at chunk level or fail whole task
                # For now, let's fail the task and rely on Celery's retry for the whole task
                raise  # Re-raise to be caught by outer try-except

        if not temp_audio_files:
            raise ValueError("No audio files were generated from chunks.")

        # Stitch audio files
        if len(temp_audio_files) == 1:
            final_audio_path_temp = temp_audio_files[0]
            final_audio_path = article_media_dir / f"article_{article_id}.mp3"
            final_audio_path_temp.rename(final_audio_path)
            logger.info(f"Single audio chunk moved to {final_audio_path}")
        else:
            combined_audio = AudioSegment.empty()
            for temp_file in temp_audio_files:
                try:
                    segment = AudioSegment.from_mp3(temp_file)
                    combined_audio += segment
                except Exception as e: # pydub can raise various errors
                    logger.error(f"Pydub error processing chunk {temp_file} for article {article_id}: {e}")
                    raise ValueError(f"Failed to process audio chunk {temp_file.name}: {e}") from e
            
            final_audio_path = article_media_dir / f"article_{article_id}.mp3"
            combined_audio.export(final_audio_path, format="mp3")
            logger.info(f"Combined {len(temp_audio_files)} audio chunks into {final_audio_path}")

        article.audio_file_path = str(final_audio_path.relative_to(media_root))
        article.status = Article.COMPLETED
        article.error_message = None # Clear any previous error
        article.save(update_fields=["audio_file_path", "status", "error_message"])
        logger.info(f"Successfully processed Article ID: {article_id}. Audio at: {article.audio_file_path}")
        return f"Article {article_id} processed successfully."

    except Exception as e:
        logger.error(f"Error processing Article ID {article_id}: {e}")
        detailed_error = traceback.format_exc()
        logger.error(detailed_error)
        
        article.status = Article.FAILED
        article.error_message = f"{type(e).__name__}: {e}\n{detailed_error[:1000]}" # Store a truncated traceback
        article.save(update_fields=["status", "error_message"])

        # Celery retry mechanism
        try:
            # self.request.retries is only available if bind=True
            if hasattr(self, 'request') and self.request.retries < self.max_retries:
                logger.info(f"Retrying task for article {article_id} ({self.request.retries + 1}/{self.max_retries})...")
                raise self.retry(exc=e, countdown=int(self.default_retry_delay * (2 ** self.request.retries)))
            else:
                logger.error(f"Max retries reached for article {article_id}. Task failed permanently.")
        except AttributeError: # If task is called directly without Celery context (e.g. in tests)
             logger.warning("Task not executed in Celery worker context, retry unavailable.")


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
