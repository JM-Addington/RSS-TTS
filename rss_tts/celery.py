"""Celery configuration for the RSS-TTS project."""

import os

from django.conf import settings

from celery import Celery  # type: ignore

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "rss_tts.settings")

app = Celery("rss_tts")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()

# Configure Celery timezone for beat schedule
app.conf.timezone = getattr(settings, "TIME_ZONE", "UTC")

# Task routing for different types of work
app.conf.task_routes = {
    "text_to_audio.parallel_tasks.generate_tts_for_chunk": {"queue": "tts_chunks"},
    "text_to_audio.parallel_tasks.stitch_audio_and_finalize": {
        "queue": "audio_processing"
    },
    "text_to_audio.tasks.process_article": {"queue": "article_processing"},
    "text_to_audio.tasks.check_stale_articles": {"queue": "maintenance"},
}

# Worker configuration
app.conf.worker_prefetch_multiplier = 1  # Prevent worker hoarding
app.conf.task_acks_late = True  # Only acknowledge after task completion
app.conf.worker_max_tasks_per_child = 100  # Prevent memory leaks

# Celery Beat Schedule
app.conf.beat_schedule = {
    "check-stale-articles-every-15-minutes": {
        "task": "text_to_audio.tasks.check_stale_articles",
        "schedule": 900.0,  # 15 minutes in seconds
    },
}
