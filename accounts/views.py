from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied
from django.http import HttpResponseForbidden, HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, ListView, UpdateView

from accounts.models_profile import UserProfile
from appconfig.models import GlobalConfig

from .forms import CustomUserCreationForm

# User is now imported directly from django.contrib.auth.models


class SuperAdminRequiredMixin:
    """Mixin to require super admin privileges."""

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated or not request.user.can_manage_users():
            return HttpResponseForbidden(
                "You don't have permission to access this page."
            )
        # Call parent dispatch method from the view class
        return super().dispatch(request, *args, **kwargs)  # type: ignore


class UserManagementView(SuperAdminRequiredMixin, LoginRequiredMixin, ListView):
    """View for listing all users for management."""

    model = User
    template_name = "accounts/user_management.html"
    context_object_name = "users"

    def get_queryset(self):
        """Return all users ordered by date joined."""
        return User.objects.all().order_by("-date_joined")


class UserCreateView(SuperAdminRequiredMixin, LoginRequiredMixin, CreateView):
    """View for creating a new user."""

    model = User
    form_class = CustomUserCreationForm
    template_name = "accounts/user_form.html"
    success_url = reverse_lazy("user-management")

    def form_valid(self, form):
        """Create user and show success message."""
        response = super().form_valid(form)
        messages.success(
            self.request, f'User "{self.object.username}" created successfully.'
        )
        return response

    def get_context_data(self, **kwargs):
        """Add context for template."""
        context = super().get_context_data(**kwargs)
        context["action"] = "Create"
        return context


@login_required
def user_approve(request, user_id):
    """Approve a user account."""
    if not request.user.can_manage_users():
        return HttpResponseForbidden(
            "You don't have permission to perform this action."
        )

    user = get_object_or_404(User, id=user_id)
    user.profile.is_approved = True
    user.profile.save()

    messages.success(request, f'User "{user.username}" has been approved.')
    return redirect("user-management")


@login_required
def user_revoke_approval(request, user_id):
    """Revoke approval for a user account."""
    if not request.user.can_manage_users():
        return HttpResponseForbidden(
            "You don't have permission to perform this action."
        )

    user = get_object_or_404(User, id=user_id)
    if user.is_super_admin:
        messages.error(request, "Cannot revoke approval for super admin users.")
        return redirect("user-management")

    user.profile.is_approved = False
    user.profile.save()

    messages.success(request, f'Approval revoked for user "{user.username}".')
    return redirect("user-management")


@login_required
def user_reset_password(request, user_id):
    """Reset a user's password."""
    if not request.user.can_manage_users():
        return HttpResponseForbidden(
            "You don't have permission to perform this action."
        )

    user = get_object_or_404(User, id=user_id)

    if request.method == "POST":
        new_password = request.POST.get("new_password")
        confirm_password = request.POST.get("confirm_password")

        if not new_password or not confirm_password:
            messages.error(request, "Both password fields are required.")
            return render(
                request, "accounts/user_reset_password.html", {"target_user": user}
            )

        if new_password != confirm_password:
            messages.error(request, "Passwords do not match.")
            return render(
                request, "accounts/user_reset_password.html", {"target_user": user}
            )

        if len(new_password) < 8:
            messages.error(request, "Password must be at least 8 characters long.")
            return render(
                request, "accounts/user_reset_password.html", {"target_user": user}
            )

        user.set_password(new_password)
        user.save()
        messages.success(
            request, f'Password reset successfully for user "{user.username}".'
        )
        return redirect("user-management")

    return render(request, "accounts/user_reset_password.html", {"target_user": user})


@login_required
def user_promote(request, user_id):
    """Promote a user to super admin."""
    if not request.user.can_manage_users():
        return HttpResponseForbidden(
            "You don't have permission to perform this action."
        )

    user = get_object_or_404(User, id=user_id)

    if user.is_super_admin:
        messages.warning(request, f'User "{user.username}" is already a super admin.')
        return redirect("user-management")

    user.profile.is_super_admin = True
    user.profile.is_approved = True
    user.profile.save()
    user.is_staff = True
    user.is_superuser = True
    user.save()

    messages.success(request, f'User "{user.username}" promoted to super admin.')
    return redirect("user-management")


@login_required
def user_demote(request, user_id):
    """Demote a user from super admin."""
    if not request.user.can_manage_users():
        return HttpResponseForbidden(
            "You don't have permission to perform this action."
        )

    user = get_object_or_404(User, id=user_id)

    if not user.is_super_admin:
        messages.warning(request, f'User "{user.username}" is not a super admin.')
        return redirect("user-management")

    super_admin_count = UserProfile.objects.filter(is_super_admin=True).count()
    if super_admin_count <= 1:
        messages.error(request, "Cannot demote the last super admin.")
        return redirect("user-management")

    user.profile.is_super_admin = False
    user.profile.save()
    user.is_staff = False
    user.is_superuser = False
    user.save()

    messages.success(request, f'User "{user.username}" demoted from super admin.')
    return redirect("user-management")


class UserDeleteView(SuperAdminRequiredMixin, LoginRequiredMixin, DeleteView):
    """View for deleting a user."""

    model = User
    template_name = "accounts/user_confirm_delete.html"
    success_url = reverse_lazy("user-management")
    pk_url_kwarg = "user_id"

    # AIDEV-NOTE: get_object() raises PermissionDenied for super admins instead of redirecting (issue #199)
    def get_object(self, queryset=None):
        """Prevent deletion of super admin users."""
        user = super().get_object(queryset)
        if user.is_super_admin:
            raise PermissionDenied("Cannot delete super admin users.")
        return user

    def form_valid(self, form):
        """Delete user with success message.

        Overrides DeleteView.form_valid() to add a success message.
        Django 5+ uses form_valid() for deletion, not delete().
        """
        username = self.object.username
        success_url = self.get_success_url()
        self.object.delete()
        messages.success(self.request, f'User "{username}" deleted successfully.')
        return HttpResponseRedirect(success_url)


class GlobalConfigView(SuperAdminRequiredMixin, LoginRequiredMixin, UpdateView):
    """View for managing global configuration settings."""

    model = GlobalConfig
    template_name = "accounts/global_config.html"
    success_url = reverse_lazy("global-config")
    fields = [
        "openai_api_key",
        "openai_title_model",
        "openai_tts_model",
        "openai_tts_voice",
        "openai_tts_response_format",
        "openai_analysis_model",
        "openai_classification_model",
        "use_gpt_for_url_extraction",
        "max_analysis_words",
        "firecrawl_api_key",
        "use_firecrawl_by_default",
        "enable_chunk_tone_llm",
        "default_tts_provider",
        "google_tts_api_key",
        "google_tts_credentials_json",
        "google_tts_default_voice_type",
        "podcast_image_url",
        "site_url",
        "rss_external_hostname",
    ]

    def get_object(self, queryset=None):
        """Get or create the global config singleton."""
        return GlobalConfig.get_or_create_with_env_migration()

    def get_form(self, form_class=None):
        """Add Bootstrap classes to form fields."""
        form = super().get_form(form_class)

        # Add Bootstrap classes to form fields
        for field_name, field in form.fields.items():
            if isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs.update({"class": "form-check-input"})
            elif isinstance(field.widget, forms.Textarea):
                field.widget.attrs.update({"class": "form-control", "rows": 3})
            else:
                field.widget.attrs.update({"class": "form-control"})

        return form

    def form_valid(self, form):
        """Save config and show success message."""
        response = super().form_valid(form)
        messages.success(self.request, "Global configuration updated successfully.")
        return response

    def get_context_data(self, **kwargs):
        """Add additional context for template."""
        context = super().get_context_data(**kwargs)
        context["conflicts"] = GlobalConfig.get_configuration_conflicts()
        return context


@login_required
def migrate_env_to_config(request):
    """View to trigger environment to database migration."""
    if not request.user.can_manage_users():
        return HttpResponseForbidden(
            "You don't have permission to perform this action."
        )

    if request.method == "POST":
        config = GlobalConfig.get_or_create_with_env_migration()

        # Force migration from environment variables
        env_mappings = {
            "openai_api_key": ("OPENAI_API_KEY", None),
            "openai_title_model": ("OPENAI_TITLE_MODEL", "gpt-4o-mini"),
            "openai_tts_model": ("OPENAI_TTS_MODEL", "tts-1-hd"),
            "openai_tts_voice": ("OPENAI_TTS_VOICE", "alloy"),
            "openai_tts_response_format": ("OPENAI_TTS_RESPONSE_FORMAT", "wav"),
            "openai_analysis_model": ("OPENAI_ANALYSIS_MODEL", "gpt-4.1"),
            "openai_classification_model": (
                "OPENAI_CLASSIFICATION_MODEL",
                "gpt-4o-mini",
            ),
            "use_gpt_for_url_extraction": ("USE_GPT_FOR_URL_EXTRACTION", True),
            "max_analysis_words": ("MAX_ANALYSIS_WORDS", 8000),
            "firecrawl_api_key": ("FIRECRAWL_API_KEY", None),
            "use_firecrawl_by_default": ("USE_FIRECRAWL_BY_DEFAULT", False),
            "enable_chunk_tone_llm": ("ENABLE_CHUNK_TONE_LLM", True),
            "default_tts_provider": ("DEFAULT_TTS_PROVIDER", "openai"),
            "google_tts_api_key": ("GOOGLE_TTS_API_KEY", None),
            "google_tts_credentials_json": ("GOOGLE_TTS_CREDENTIALS_JSON", None),
            "google_tts_default_voice_type": (
                "GOOGLE_TTS_DEFAULT_VOICE_TYPE",
                "gemini",
            ),
            "podcast_image_url": ("PODCAST_IMAGE_URL", None),
            "site_url": ("SITE_URL", "http://localhost:8000"),
            "rss_external_hostname": ("RSS_EXTERNAL_HOSTNAME", None),
        }

        # AIDEV-NOTE: POST data is always a string; must parse explicitly to avoid "false" being truthy
        force = request.POST.get("force", "").lower() in ("true", "1", "yes", "on")
        migrated_count = 0

        from django.conf import settings

        for field_name, (env_var, default) in env_mappings.items():
            env_value = getattr(settings, env_var, default)
            current_value = getattr(config, field_name)

            if env_value is not None and (force or not current_value):
                # Convert string boolean values
                if isinstance(default, bool) and isinstance(env_value, str):
                    env_value = env_value.lower() in ("true", "1", "yes", "on")

                # Convert string integer values
                if isinstance(default, int) and isinstance(env_value, str):
                    try:
                        env_value = int(env_value)
                    except ValueError:
                        continue

                setattr(config, field_name, env_value)
                migrated_count += 1

        if migrated_count > 0:
            config.save()
            messages.success(
                request,
                f"Successfully migrated {migrated_count} settings from environment variables.",
            )
        else:
            messages.info(
                request, "No settings were migrated (all database values already set)."
            )

        return redirect("global-config")

    return redirect("global-config")
