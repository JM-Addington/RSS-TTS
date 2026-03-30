"""Tests for the custom DRF exception handler."""

from django.test import TestCase
from rest_framework import status
from rest_framework.exceptions import (
    APIException,
    NotFound,
    Throttled,
    ValidationError,
)
from rest_framework.test import APIRequestFactory

from text_to_audio.exception_handler import api_exception_handler


class ExceptionHandlerTests(TestCase):
    """Unit tests for api_exception_handler."""

    def setUp(self):
        """Set up a fake DRF context for the handler."""
        factory = APIRequestFactory()
        request = factory.get("/fake/")
        self.context = {"request": request, "view": None}

    def _call_handler(self, exc):
        """Helper to invoke the exception handler."""
        return api_exception_handler(exc, self.context)

    def test_field_level_validation_error(self):
        """Field-level errors get wrapped in envelope with 'fields' key."""
        exc = ValidationError({"speed": ["Ensure this value is less than or equal to 4.0."]})
        response = self._call_handler(exc)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["error"], "Validation failed.")
        self.assertIn("fields", response.data)
        self.assertEqual(
            response.data["fields"]["speed"],
            ["Ensure this value is less than or equal to 4.0."],
        )

    def test_non_field_validation_error_string(self):
        """Non-field ValidationError(string) becomes {"error": "msg"}.

        DRF wraps string errors as {"non_field_errors": ["msg"]}.
        """
        exc = ValidationError("You must provide either text_content or source_url.")
        response = self._call_handler(exc)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            response.data["error"],
            "You must provide either text_content or source_url.",
        )
        self.assertNotIn("fields", response.data)

    def test_non_field_validation_error_list(self):
        """Non-field ValidationError(list) picks the first message."""
        exc = ValidationError(["First error.", "Second error."])
        response = self._call_handler(exc)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["error"], "First error.")
        self.assertNotIn("fields", response.data)

    def test_not_found_error(self):
        """NotFound exception produces {"error": "..."}."""
        exc = NotFound("Feed not found.")
        response = self._call_handler(exc)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(response.data["error"], "Feed not found.")

    def test_throttled_error(self):
        """Throttled exception produces {"error": "Request was throttled..."}."""
        exc = Throttled(wait=30)
        response = self._call_handler(exc)
        self.assertEqual(response.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
        self.assertIn("throttled", response.data["error"].lower())

    def test_generic_api_exception(self):
        """Generic APIException produces {"error": "message"}."""
        exc = APIException("Something went wrong.")
        response = self._call_handler(exc)
        self.assertEqual(response.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)
        self.assertEqual(response.data["error"], "Something went wrong.")

    def test_non_drf_exception_returns_none(self):
        """Non-DRF exceptions (e.g. ValueError) return None to let Django handle."""
        exc = ValueError("not a DRF exception")
        response = self._call_handler(exc)
        self.assertIsNone(response)

    def test_existing_error_key_passes_through(self):
        """Response already containing {"error": ...} passes through unchanged."""
        exc = ValidationError({"error": "Already formatted."})
        response = self._call_handler(exc)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["error"], "Already formatted.")
        self.assertNotIn("fields", response.data)

    def test_multiple_field_errors(self):
        """Multiple field-level errors all appear under 'fields'."""
        exc = ValidationError({
            "speed": ["Too fast."],
            "voice_id": ["Invalid voice."],
        })
        response = self._call_handler(exc)
        self.assertEqual(response.data["error"], "Validation failed.")
        self.assertIn("speed", response.data["fields"])
        self.assertIn("voice_id", response.data["fields"])

    def test_empty_list_validation_error(self):
        """Empty list ValidationError falls back to generic message."""
        exc = ValidationError([])
        response = self._call_handler(exc)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["error"], "Validation failed.")
