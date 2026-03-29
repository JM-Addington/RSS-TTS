"""Integration tests for /api/schema/ and /api/docs/ access control."""

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework import status
from rest_framework.test import APIClient

User = get_user_model()


class SchemaEndpointAccessTests(TestCase):
    """Integration tests for API schema/docs endpoint permissions."""

    def setUp(self):
        self.client = APIClient()
        self.staff_user = User.objects.create_user(
            username="staffuser", password="testpass", is_staff=True
        )
        self.normal_user = User.objects.create_user(
            username="normaluser", password="testpass", is_staff=False
        )

    @override_settings(DEBUG=False)
    def test_anonymous_denied_schema(self):
        """Anonymous user gets 403 on /api/schema/ in production."""
        response = self.client.get("/api/schema/")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    @override_settings(DEBUG=False)
    def test_anonymous_denied_docs(self):
        """Anonymous user gets 403 on /api/docs/ in production."""
        response = self.client.get("/api/docs/")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    @override_settings(DEBUG=False)
    def test_non_staff_denied_schema(self):
        """Non-staff authenticated user gets 403 on /api/schema/."""
        self.client.force_authenticate(user=self.normal_user)
        response = self.client.get("/api/schema/")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    @override_settings(DEBUG=False)
    def test_staff_allowed_schema(self):
        """Staff user gets 200 on /api/schema/."""
        self.client.force_authenticate(user=self.staff_user)
        response = self.client.get("/api/schema/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    @override_settings(DEBUG=False)
    def test_staff_allowed_docs(self):
        """Staff user gets 200 on /api/docs/."""
        self.client.force_authenticate(user=self.staff_user)
        response = self.client.get("/api/docs/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    @override_settings(DEBUG=True)
    def test_debug_anonymous_allowed_schema(self):
        """Anonymous user gets 200 on /api/schema/ in DEBUG mode."""
        response = self.client.get("/api/schema/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    @override_settings(DEBUG=True)
    def test_debug_anonymous_allowed_docs(self):
        """Anonymous user gets 200 on /api/docs/ in DEBUG mode."""
        response = self.client.get("/api/docs/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
