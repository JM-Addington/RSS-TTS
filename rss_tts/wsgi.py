"""WSGI config for rss_tts project."""

import os
from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "rss_tts.settings")

application = get_wsgi_application()
