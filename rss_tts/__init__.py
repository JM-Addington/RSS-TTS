"""RSS-TTS Django project package.

This package contains the main Django project configuration.
"""

from .celery import app as celery_app

__all__ = ["celery_app"]
