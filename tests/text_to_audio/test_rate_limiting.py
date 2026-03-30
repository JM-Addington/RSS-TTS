# flake8: noqa
# mypy: ignore-errors
"""Tests for rate limiting on TTS-triggering endpoints (issue #200).

Verifies that voice_preset_test and voice_preset_sample endpoints
have per-user rate limiting to prevent TTS API quota exhaustion.
"""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings

from text_to_audio.models import Feed, UserVoicePreset

User = get_user_model()

# AIDEV-NOTE: django-ratelimit uses Django's cache backend for rate tracking.
# Tests use LocMemCache to avoid needing Redis in the test environment.
RATELIMIT_TEST_CACHE = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "ratelimit-test",
    }
}


@override_settings(CACHES=RATELIMIT_TEST_CACHE, RATELIMIT_USE_CACHE="default")
class VoicePresetTestRateLimitTests(TestCase):
    """Test rate limiting on the voice_preset_test endpoint."""

    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(
            username="ratelimit_user", password="testpass"
        )
        self.client.login(username="ratelimit_user", password="testpass")
        self.url = "/presets/voice/test/"

    def _make_tts_request(self):
        """Make a valid POST request to the voice_preset_test endpoint."""
        return self.client.post(
            self.url,
            data={
                "voice_id": "alloy",
                "speed": "1.0",
                "text": "Hello world test",
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

    @patch("text_to_audio.services.tts_service.TTSService.generate_speech")
    def test_requests_within_limit_succeed(self, mock_tts):
        """Requests within the rate limit should succeed normally."""
        mock_tts.return_value = b"\x00" * 100  # fake audio data
        response = self._make_tts_request()
        # Should get 200 (audio file response), not 429
        self.assertNotEqual(response.status_code, 429)

    @patch("text_to_audio.services.tts_service.TTSService.generate_speech")
    def test_excessive_requests_are_rate_limited(self, mock_tts):
        """Requests exceeding the rate limit should return 429."""
        mock_tts.return_value = b"\x00" * 100

        # Make requests until we get rate limited
        # The limit should be 10/minute per the issue suggestion
        got_429 = False
        for i in range(15):
            response = self._make_tts_request()
            if response.status_code == 429:
                got_429 = True
                break

        self.assertTrue(got_429, "Expected 429 response after exceeding rate limit")

    @patch("text_to_audio.services.tts_service.TTSService.generate_speech")
    def test_rate_limit_is_per_user(self, mock_tts):
        """Rate limiting should be per-user, not global."""
        mock_tts.return_value = b"\x00" * 100

        # Exhaust rate limit for user 1
        for i in range(12):
            self._make_tts_request()

        # Create and login as a different user
        user2 = User.objects.create_user(
            username="ratelimit_user2", password="testpass2"
        )
        self.client.login(username="ratelimit_user2", password="testpass2")

        # User 2 should not be rate limited
        response = self._make_tts_request()
        self.assertNotEqual(
            response.status_code, 429, "User 2 should not be rate limited"
        )

    def test_unauthenticated_request_rejected(self):
        """Unauthenticated requests should be rejected (login_required)."""
        self.client.logout()
        response = self._make_tts_request()
        # Should redirect to login, not allow through
        self.assertEqual(response.status_code, 302)


@override_settings(CACHES=RATELIMIT_TEST_CACHE, RATELIMIT_USE_CACHE="default")
class VoicePresetSampleRateLimitTests(TestCase):
    """Test rate limiting on the voice_preset_sample endpoint."""

    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(
            username="sample_user", password="testpass"
        )
        self.client.login(username="sample_user", password="testpass")
        self.feed = Feed.objects.create(user=self.user, name="Test Feed")
        self.preset = UserVoicePreset.objects.create(
            user=self.user,
            name="Test Preset",
            voice_id="alloy",
            speed=1.0,
        )
        self.url = f"/presets/voice/{self.preset.id}/sample/"

    def _make_sample_request(self):
        """Make a valid POST request to the voice_preset_sample endpoint."""
        return self.client.post(
            self.url,
            data={"text": "Hello world sample"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

    @patch("text_to_audio.services.tts_service.TTSService.generate_speech")
    def test_requests_within_limit_succeed(self, mock_tts):
        """Requests within the rate limit should succeed normally."""
        mock_tts.return_value = b"\x00" * 100
        response = self._make_sample_request()
        self.assertNotEqual(response.status_code, 429)

    @patch("text_to_audio.services.tts_service.TTSService.generate_speech")
    def test_excessive_requests_are_rate_limited(self, mock_tts):
        """Requests exceeding the rate limit should return 429."""
        mock_tts.return_value = b"\x00" * 100

        got_429 = False
        for i in range(15):
            response = self._make_sample_request()
            if response.status_code == 429:
                got_429 = True
                break

        self.assertTrue(got_429, "Expected 429 response after exceeding rate limit")


@override_settings(CACHES=RATELIMIT_TEST_CACHE, RATELIMIT_USE_CACHE="default")
class RateLimitResponseTests(TestCase):
    """Test the custom rate limit response handler."""

    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(
            username="response_user", password="testpass"
        )
        self.client.login(username="response_user", password="testpass")

    @patch("text_to_audio.services.tts_service.TTSService.generate_speech")
    def test_rate_limit_response_is_429(self, mock_tts):
        """Rate limited response should have HTTP 429 status code."""
        mock_tts.return_value = b"\x00" * 100
        url = "/presets/voice/test/"

        last_response = None
        for i in range(15):
            last_response = self.client.post(
                url,
                data={
                    "voice_id": "alloy",
                    "speed": "1.0",
                    "text": "Test rate limit response",
                },
                HTTP_X_REQUESTED_WITH="XMLHttpRequest",
            )
            if last_response.status_code == 429:
                break

        self.assertEqual(last_response.status_code, 429)

    @patch("text_to_audio.services.tts_service.TTSService.generate_speech")
    def test_rate_limit_response_has_retry_after(self, mock_tts):
        """Rate limited response should include Retry-After header."""
        mock_tts.return_value = b"\x00" * 100
        url = "/presets/voice/test/"

        for i in range(15):
            response = self.client.post(
                url,
                data={
                    "voice_id": "alloy",
                    "speed": "1.0",
                    "text": "Test retry after",
                },
                HTTP_X_REQUESTED_WITH="XMLHttpRequest",
            )
            if response.status_code == 429:
                self.assertIn(
                    "Retry-After",
                    response,
                    "Rate limited response should have Retry-After header",
                )
                return

        self.fail("Never got rate limited")
