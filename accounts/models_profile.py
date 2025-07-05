from django.contrib.auth.models import User
from django.db import models, transaction
from django.db.models.signals import post_save
from django.dispatch import receiver


class UserProfile(models.Model):
    """
    Extended user profile that adds user management fields to Django's User model.
    This approach allows us to add new functionality without changing AUTH_USER_MODEL.
    """

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")

    is_approved = models.BooleanField(
        default=False,
        help_text="Designates whether this user has been approved by an admin.",
    )
    is_super_admin = models.BooleanField(
        default=False,
        help_text="Designates whether this user is a super admin who can manage other users.",
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "accounts_userprofile"
        verbose_name = "User Profile"
        verbose_name_plural = "User Profiles"

    def __str__(self):
        return f"Profile for {self.user.username}"

    def save(self, *args, **kwargs):
        # AIDEV-NOTE: First user created becomes super admin automatically
        # Use atomic transaction with select_for_update to prevent race conditions
        with transaction.atomic():
            if not UserProfile.objects.select_for_update().exists():
                self.is_approved = True
                self.is_super_admin = True
                # Also make the Django user staff and superuser
                self.user.is_staff = True
                self.user.is_superuser = True
                self.user.save()
        super().save(*args, **kwargs)

    def can_manage_users(self):
        """Check if user can manage other users."""
        return self.is_super_admin and self.is_approved


# AIDEV-NOTE: Signals to automatically create/save UserProfile when User is created/saved
@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    """Create a UserProfile when a User is created."""
    if created:
        UserProfile.objects.create(user=instance)


# Note: We don't need a save signal since UserProfile is saved separately


# Helper functions to extend Django's User model
def user_is_approved(self):
    """Check if user is approved."""
    return hasattr(self, "profile") and self.profile.is_approved


def user_is_super_admin(self):
    """Check if user is super admin."""
    return hasattr(self, "profile") and self.profile.is_super_admin


def user_can_manage_users(self):
    """Check if user can manage other users."""
    return hasattr(self, "profile") and self.profile.can_manage_users()


def user_get_approval_status(self):
    """Get user approval status display."""
    if not hasattr(self, "profile"):
        return "No Profile"
    if self.profile.is_super_admin:
        return "Super Admin"
    elif self.profile.is_approved:
        return "Approved"
    else:
        return "Pending"


# Add methods to Django's User model
User.add_to_class("is_approved", property(user_is_approved))
User.add_to_class("is_super_admin", property(user_is_super_admin))
User.add_to_class("can_manage_users", user_can_manage_users)
User.add_to_class("get_approval_status", user_get_approval_status)
