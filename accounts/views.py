from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.models import User
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, ListView, UpdateView

from .forms import CustomUserCreationForm

# User is now imported directly from django.contrib.auth.models


class SuperAdminRequiredMixin:
    """Mixin to require super admin privileges."""

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated or not request.user.can_manage_users():
            return HttpResponseForbidden(
                "You don't have permission to access this page."
            )
        return super().dispatch(request, *args, **kwargs)


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


class UserDeleteView(SuperAdminRequiredMixin, LoginRequiredMixin, DeleteView):
    """View for deleting a user."""

    model = User
    template_name = "accounts/user_confirm_delete.html"
    success_url = reverse_lazy("user-management")
    pk_url_kwarg = "user_id"

    def get_object(self):
        """Prevent deletion of super admin users."""
        user = super().get_object()
        if user.is_super_admin:
            messages.error(self.request, "Cannot delete super admin users.")
            return redirect("user-management")
        return user

    def delete(self, request, *args, **kwargs):
        """Delete user with success message."""
        self.object = self.get_object()
        username = self.object.username
        response = super().delete(request, *args, **kwargs)
        messages.success(request, f'User "{username}" deleted successfully.')
        return response
