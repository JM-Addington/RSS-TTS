from django.urls import path

from . import views

urlpatterns = [
    path("users/", views.UserManagementView.as_view(), name="user-management"),
    path("users/create/", views.UserCreateView.as_view(), name="user-create"),
    path("users/<int:user_id>/approve/", views.user_approve, name="user-approve"),
    path(
        "users/<int:user_id>/revoke/",
        views.user_revoke_approval,
        name="user-revoke-approval",
    ),
    path(
        "users/<int:user_id>/reset-password/",
        views.user_reset_password,
        name="user-reset-password",
    ),
    path("users/<int:user_id>/promote/", views.user_promote, name="user-promote"),
    path("users/<int:user_id>/demote/", views.user_demote, name="user-demote"),
    path(
        "users/<int:user_id>/delete/",
        views.UserDeleteView.as_view(),
        name="user-delete",
    ),
]
