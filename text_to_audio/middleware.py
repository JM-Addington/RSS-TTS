"""Middleware for text_to_audio app."""

import logging

from django.http import HttpResponse

logger = logging.getLogger(__name__)


class RateLimitMiddleware:
    """Convert django-ratelimit's Ratelimited exception to HTTP 429.

    django-ratelimit raises Ratelimited (a PermissionDenied subclass) which
    Django renders as 403. This middleware catches it and returns a proper
    429 Too Many Requests response with a Retry-After header.
    """

    # AIDEV-NOTE: must be placed before SecurityMiddleware in MIDDLEWARE list (issue #200)
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_exception(self, request, exception):
        from django_ratelimit.exceptions import Ratelimited

        if isinstance(exception, Ratelimited):
            logger.warning(
                "Rate limit exceeded for user=%s on %s",
                getattr(request.user, "username", "anonymous"),
                request.path,
            )
            response = HttpResponse(
                "Rate limit exceeded. Please try again later.",
                status=429,
                content_type="text/plain",
            )
            response["Retry-After"] = "60"
            return response
        return None
