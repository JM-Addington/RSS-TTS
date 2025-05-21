"""Celery tasks for processing articles."""

from __future__ import annotations

import uuid
from pathlib import Path

from celery import shared_task  # type: ignore
from django.conf import settings

from .models import Article


@shared_task
def process_article(article_id: int) -> int:
    """Process an article and generate a placeholder MP3 file.

    This simplified task writes the article text to a fake MP3 file and
    marks the article as completed. In a real implementation this would
    call external services for extraction and TTS conversion.
    
    Args:
        article_id: The ID of the article to process
        
    Returns:
        The article ID
        
    Raises:
        Exception: If processing fails
    """
    try:
        article = Article.objects.get(id=article_id)

        # Ensure media directory exists
        media_root = Path(settings.BASE_DIR) / "media"
        media_root.mkdir(exist_ok=True)

        # Create a more unique filename with user_id and a random component
        unique_id = uuid.uuid4().hex[:8]
        file_path = media_root / f"article_{article.feed.user.id}_{article_id}_{unique_id}.mp3"
        
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(article.text_content)

        article.audio_file_path = str(file_path)
        article.status = Article.COMPLETED
        article.save(update_fields=["audio_file_path", "status"])
        return article_id
    except Exception as e:
        # If we can access the article, mark it as failed
        try:
            article = Article.objects.get(id=article_id)
            article.status = Article.FAILED
            article.save(update_fields=["status"])
        except:
            pass  # If we can't get the article, just let the exception propagate
        raise  # Re-raise the original exception
