"""rss_tts URL Configuration."""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import path

from text_to_audio.views import (
    ArticleCreateView,
    ArticleListView,
    ArticleMediaView,
    HomeView,
    SignUpView,
)

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/login/", auth_views.LoginView.as_view(), name="login"),
    path("accounts/logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("accounts/signup/", SignUpView.as_view(), name="signup"),
    path("articles/", ArticleListView.as_view(), name="article-list"),
    path("articles/submit/", ArticleCreateView.as_view(), name="article-submit"),
    path(
        "articles/<int:article_id>/media/",
        ArticleMediaView.as_view(),
        name="article-media",
    ),
    path("", HomeView.as_view(), name="home"),
]

# Serve media files in development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
