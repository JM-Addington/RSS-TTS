from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User
from django.utils.html import format_html
from .models_profile import UserProfile


class UserProfileInline(admin.StackedInline):
    """Inline admin for UserProfile."""
    model = UserProfile
    can_delete = False
    verbose_name_plural = 'User Management Settings'
    fields = ('is_approved', 'is_super_admin', 'created_at', 'updated_at')
    readonly_fields = ('created_at', 'updated_at')


class UserAdmin(BaseUserAdmin):
    """Extended UserAdmin that includes UserProfile management."""
    inlines = (UserProfileInline,)

    list_display = ('username', 'email', 'first_name', 'last_name', 'approval_status', 'super_admin_status', 'date_joined')
    list_filter = BaseUserAdmin.list_filter + ('profile__is_approved', 'profile__is_super_admin')

    def approval_status(self, obj):
        if hasattr(obj, 'profile'):
            if obj.profile.is_approved:
                return format_html('<span style="color: green;">✓ Approved</span>')
            return format_html('<span style="color: red;">✗ Pending</span>')
        return format_html('<span style="color: gray;">No Profile</span>')
    approval_status.short_description = 'Approval Status'

    def super_admin_status(self, obj):
        if hasattr(obj, 'profile') and obj.profile.is_super_admin:
            return format_html('<span style="color: blue;">★ Super Admin</span>')
        return format_html('<span style="color: gray;">Regular User</span>')
    super_admin_status.short_description = 'User Type'

    actions = ['approve_users', 'revoke_approval', 'make_super_admin', 'remove_super_admin']

    def approve_users(self, request, queryset):
        updated = 0
        for user in queryset:
            if hasattr(user, 'profile'):
                user.profile.is_approved = True
                user.profile.save()
                updated += 1
        self.message_user(request, f'{updated} user(s) approved successfully.')
    approve_users.short_description = "Approve selected users"

    def revoke_approval(self, request, queryset):
        updated = 0
        for user in queryset:
            if hasattr(user, 'profile') and not user.profile.is_super_admin:
                user.profile.is_approved = False
                user.profile.save()
                updated += 1
        self.message_user(request, f'{updated} user(s) approval revoked.')
    revoke_approval.short_description = "Revoke approval for selected users"

    def make_super_admin(self, request, queryset):
        updated = 0
        for user in queryset:
            if hasattr(user, 'profile'):
                user.profile.is_super_admin = True
                user.profile.is_approved = True
                user.profile.save()
                user.is_staff = True
                user.is_superuser = True
                user.save()
                updated += 1
        self.message_user(request, f'{updated} user(s) made super admin.')
    make_super_admin.short_description = "Make selected users super admin"

    def remove_super_admin(self, request, queryset):
        updated = 0
        for user in queryset:
            if hasattr(user, 'profile') and user.profile.is_super_admin:
                # Check if this is the last super admin
                super_admin_count = UserProfile.objects.filter(is_super_admin=True).count()
                if super_admin_count > 1:
                    user.profile.is_super_admin = False
                    user.profile.save()
                    user.is_staff = False
                    user.is_superuser = False
                    user.save()
                    updated += 1
        self.message_user(request, f'{updated} user(s) removed from super admin.')
    remove_super_admin.short_description = "Remove super admin status"


# Re-register UserAdmin
admin.site.unregister(User)
admin.site.register(User, UserAdmin)

# Also register UserProfile separately for direct management
@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    """Admin for UserProfile model."""
    list_display = ('user', 'is_approved', 'is_super_admin', 'created_at')
    list_filter = ('is_approved', 'is_super_admin', 'created_at')
    search_fields = ('user__username', 'user__email')
    readonly_fields = ('created_at', 'updated_at')
