"""Celery configuration for the RSS-TTS project."""

import os

from celery import Celery  # type: ignore
from django.conf import settings

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "rss_tts.settings")

app = Celery("rss_tts")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()

# Configure Celery timezone for beat schedule
app.conf.timezone = getattr(settings, "TIME_ZONE", "UTC")

# Celery Beat Schedule
app.conf.beat_schedule = {
    "check-stale-articles-every-15-minutes": {
        "task": "text_to_audio.tasks.check_stale_articles",
        "schedule": 900.0,  # 15 minutes in seconds
    },
}
