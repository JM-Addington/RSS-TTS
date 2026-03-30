"""Tests for the IsStaffOrDebug permission class."""

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework.test import APIRequestFactory

from text_to_audio.permissions import IsStaffOrDebug

User = get_user_model()


class IsStaffOrDebugPermissionTests(TestCase):
    """Unit tests for IsStaffOrDebug permission."""

    def setUp(self):
        self.factory = APIRequestFactory()
        self.permission = IsStaffOrDebug()
        self.staff_user = User.objects.create_user(
            username="staffuser", password="testpass", is_staff=True
        )
        self.normal_user = User.objects.create_user(
            username="normaluser", password="testpass", is_staff=False
        )

    @override_settings(DEBUG=True)
    def test_debug_mode_allows_anonymous(self):
        """In DEBUG mode, anonymous users can access."""
        from django.contrib.auth.models import AnonymousUser

        request = self.factory.get("/api/schema/")
        request.user = AnonymousUser()
        self.assertTrue(self.permission.has_permission(request, None))

    @override_settings(DEBUG=True)
    def test_debug_mode_allows_any_authenticated_user(self):
        """In DEBUG mode, any authenticated user can access."""
        request = self.factory.get("/api/schema/")
        request.user = self.normal_user
        self.assertTrue(self.permission.has_permission(request, None))

    @override_settings(DEBUG=False)
    def test_production_denies_anonymous(self):
        """In production, anonymous users are denied."""
        from django.contrib.auth.models import AnonymousUser

        request = self.factory.get("/api/schema/")
        request.user = AnonymousUser()
        self.assertFalse(self.permission.has_permission(request, None))

    @override_settings(DEBUG=False)
    def test_production_denies_non_staff(self):
        """In production, non-staff authenticated users are denied."""
        request = self.factory.get("/api/schema/")
        request.user = self.normal_user
        self.assertFalse(self.permission.has_permission(request, None))

    @override_settings(DEBUG=False)
    def test_production_allows_staff(self):
        """In production, staff users are allowed."""
        request = self.factory.get("/api/schema/")
        request.user = self.staff_user
        self.assertTrue(self.permission.has_permission(request, None))
