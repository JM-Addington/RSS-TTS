from django.contrib import messages
from django.contrib.auth import logout
from django.shortcuts import redirect
from django.urls import reverse


class AdminApprovalRequiredMiddleware:
    """
    Middleware that ensures only approved users can access the application.
    Super admins bypass this requirement.
    """

    def __init__(self, get_response):
        self.get_response = get_response
        # AIDEV-NOTE: URLs that don't require admin approval
        self.exempt_urls = [
            reverse("login"),
            reverse("logout"),
            reverse("signup"),
            reverse("admin:index"),
            "/admin/",
            "/static/",
            "/media/",
            "/api/",  # API endpoints might need their own auth
        ]

    def __call__(self, request):
        # Check if user is authenticated and not approved
        # AIDEV-NOTE: Check for profile existence before accessing is_approved
        if (
            request.user.is_authenticated
            and hasattr(request.user, "profile")
            and not request.user.is_approved
            and not request.path.startswith(tuple(self.exempt_urls))
        ):

            # Log them out and redirect to login with message
            logout(request)
            try:
                messages.warning(
                    request,
                    "Your account is pending admin approval. Please wait for an administrator to approve your account.",
                )
            except Exception:
                # If messages framework not available, continue without message
                pass
            return redirect("login")

        response = self.get_response(request)
        return response
