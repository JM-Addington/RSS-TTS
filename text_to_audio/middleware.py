"""Rate limiting middleware for TTS endpoints.

AIDEV-NOTE: Catches django-ratelimit's Ratelimited exception and returns
HTTP 429 with Retry-After header instead of the default 403.
"""

import json

from django.http import HttpResponse
from django.utils.deprecation import MiddlewareMixin
from django_ratelimit.exceptions import Ratelimited


class RateLimitMiddleware(MiddlewareMixin):
    """Convert django-ratelimit Ratelimited exceptions to HTTP 429 responses."""

    def process_exception(self, request, exception):
        if isinstance(exception, Ratelimited):
            return HttpResponse(
                json.dumps({"error": "Rate limit exceeded. Please try again later."}),
                content_type="application/json",
                status=429,
                headers={"Retry-After": "60"},
            )
        return None
