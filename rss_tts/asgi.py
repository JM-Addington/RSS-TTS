"""ASGI config for rss_tts project."""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "rss_tts.settings")

application = get_asgi_application()
