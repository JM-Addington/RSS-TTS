# flake8: noqa
# mypy: ignore-errors
"""Tests for rate limiting on TTS voice preset endpoints.

AIDEV-NOTE: These tests verify django-ratelimit integration on voice_preset_test
and voice_preset_sample views. Rate limit: 10/min per authenticated user.
"""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.http import HttpRequest, HttpResponse
from django.test import Client, TestCase, override_settings

from text_to_audio.models import UserVoicePreset

User = get_user_model()

# Use LocMemCache for tests to avoid Redis dependency
TEST_CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "rate-limit-tests",
    }
}


@override_settings(CACHES=TEST_CACHES, RATELIMIT_USE_CACHE="default")
class RateLimitMiddlewareUnitTest(TestCase):
    """Unit tests for the RateLimitMiddleware."""

    def test_middleware_converts_ratelimited_to_429(self):
        """process_exception catches Ratelimited and returns 429."""
        from django_ratelimit.exceptions import Ratelimited

        from text_to_audio.middleware import RateLimitMiddleware

        middleware = RateLimitMiddleware(lambda r: HttpResponse("OK"))
        request = HttpRequest()
        response = middleware.process_exception(request, Ratelimited())

        self.assertEqual(response.status_code, 429)

    def test_middleware_includes_retry_after_header(self):
        """429 response includes Retry-After header."""
        from django_ratelimit.exceptions import Ratelimited

        from text_to_audio.middleware import RateLimitMiddleware

        middleware = RateLimitMiddleware(lambda r: HttpResponse("OK"))
        request = HttpRequest()
        response = middleware.process_exception(request, Ratelimited())

        self.assertIn("Retry-After", response)
        self.assertEqual(response["Retry-After"], "60")

    def test_middleware_ignores_other_exceptions(self):
        """process_exception returns None for non-Ratelimited exceptions."""
        from text_to_audio.middleware import RateLimitMiddleware

        middleware = RateLimitMiddleware(lambda r: HttpResponse("OK"))
        request = HttpRequest()
        result = middleware.process_exception(request, ValueError("test"))

        self.assertIsNone(result)

    def test_middleware_passes_through_normal_responses(self):
        """Middleware does not interfere with normal responses."""
        from text_to_audio.middleware import RateLimitMiddleware

        middleware = RateLimitMiddleware(lambda r: HttpResponse("OK", status=200))
        request = HttpRequest()
        response = middleware(request)

        self.assertEqual(response.status_code, 200)


@override_settings(CACHES=TEST_CACHES, RATELIMIT_USE_CACHE="default")
class VoicePresetTestRateLimitTest(TestCase):
    """Tests for rate limiting on the voice_preset_test endpoint."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username="ratelimituser", password="testpass")
        self.client.login(username="ratelimituser", password="testpass")
        # Clear rate limit cache between tests
        from django.core.cache import cache

        cache.clear()

    @patch("text_to_audio.services.tts_service.TTSService")
    def test_within_limit_requests_succeed(self, mock_tts_cls):
        """Requests within the rate limit return normal responses."""
        mock_tts_cls.return_value.generate_speech.return_value = b"\x00" * 100

        response = self.client.post(
            "/presets/voice/test/",
            {"voice_id": "alloy", "speed": "1.0", "text": "Hello world"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        # Should succeed (200) not be rate limited (429)
        self.assertNotEqual(response.status_code, 429)

    @patch("text_to_audio.services.tts_service.TTSService")
    def test_excessive_requests_get_429(self, mock_tts_cls):
        """Requests exceeding the rate limit return HTTP 429."""
        mock_tts_cls.return_value.generate_speech.return_value = b"\x00" * 100

        # Make 11 requests (limit is 10/min)
        for i in range(11):
            response = self.client.post(
                "/presets/voice/test/",
                {"voice_id": "alloy", "speed": "1.0", "text": f"Hello world {i}"},
                HTTP_X_REQUESTED_WITH="XMLHttpRequest",
            )

        # The 11th request should be rate limited
        self.assertEqual(response.status_code, 429)

    @patch("text_to_audio.services.tts_service.TTSService")
    def test_retry_after_header_present(self, mock_tts_cls):
        """429 response includes Retry-After header."""
        mock_tts_cls.return_value.generate_speech.return_value = b"\x00" * 100

        for i in range(11):
            response = self.client.post(
                "/presets/voice/test/",
                {"voice_id": "alloy", "speed": "1.0", "text": f"Hello world {i}"},
                HTTP_X_REQUESTED_WITH="XMLHttpRequest",
            )

        self.assertEqual(response.status_code, 429)
        self.assertIn("Retry-After", response)

    def test_unauthenticated_users_redirected(self):
        """Unauthenticated users are redirected to login."""
        self.client.logout()
        response = self.client.post(
            "/presets/voice/test/",
            {"voice_id": "alloy", "speed": "1.0", "text": "Hello"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 302)


@override_settings(CACHES=TEST_CACHES, RATELIMIT_USE_CACHE="default")
class VoicePresetSampleRateLimitTest(TestCase):
    """Tests for rate limiting on the voice_preset_sample endpoint."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username="ratelimituser2", password="testpass"
        )
        self.client.login(username="ratelimituser2", password="testpass")
        self.preset = UserVoicePreset.objects.create(
            user=self.user,
            name="Test Preset",
            voice_id="alloy",
            speed=1.0,
        )
        from django.core.cache import cache

        cache.clear()

    @patch("text_to_audio.services.tts_service.TTSService")
    def test_within_limit_requests_succeed(self, mock_tts_cls):
        """Requests within the rate limit return normal responses."""
        mock_tts_cls.return_value.generate_speech.return_value = b"\x00" * 100

        response = self.client.post(
            f"/presets/voice/{self.preset.id}/sample/",
            {"text": "Hello world"},
        )
        self.assertNotEqual(response.status_code, 429)

    @patch("text_to_audio.services.tts_service.TTSService")
    def test_excessive_requests_get_429(self, mock_tts_cls):
        """Requests exceeding the rate limit return HTTP 429."""
        mock_tts_cls.return_value.generate_speech.return_value = b"\x00" * 100

        for i in range(11):
            response = self.client.post(
                f"/presets/voice/{self.preset.id}/sample/",
                {"text": f"Hello world {i}"},
            )

        self.assertEqual(response.status_code, 429)

    @patch("text_to_audio.services.tts_service.TTSService")
    def test_per_user_isolation(self, mock_tts_cls):
        """One user hitting the limit doesn't affect another user."""
        mock_tts_cls.return_value.generate_speech.return_value = b"\x00" * 100

        # User 1 exhausts the limit
        for i in range(11):
            self.client.post(
                f"/presets/voice/{self.preset.id}/sample/",
                {"text": f"Hello {i}"},
            )

        # User 2 should still be able to make requests
        user2 = User.objects.create_user(username="ratelimituser3", password="testpass")
        preset2 = UserVoicePreset.objects.create(
            user=user2, name="Test Preset 2", voice_id="alloy", speed=1.0
        )
        client2 = Client()
        client2.login(username="ratelimituser3", password="testpass")

        response = client2.post(
            f"/presets/voice/{preset2.id}/sample/",
            {"text": "Hello from user 2"},
        )
        self.assertNotEqual(response.status_code, 429)
