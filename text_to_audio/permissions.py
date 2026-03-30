"""Custom DRF permission classes."""

from django.conf import settings
from rest_framework.permissions import BasePermission


class IsStaffOrDebug(BasePermission):
    """Allow access if DEBUG is on, or if the user is authenticated staff."""

    # AIDEV-NOTE: Used on /api/schema/ and /api/docs/ to restrict OpenAPI spec in production
    def has_permission(self, request, view):
        if settings.DEBUG:
            return True
        return request.user and request.user.is_authenticated and request.user.is_staff
