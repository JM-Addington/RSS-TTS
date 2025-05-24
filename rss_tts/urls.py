"""rss_tts URL Configuration."""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import path

from text_to_audio.feeds import UserFeed
from text_to_audio.views import (
    ArticleCreateView,
    ArticleListView,
    ArticleMediaView,
    FeedArticleCreateView,
    FeedArticleListView,
    FeedCreateView,
    FeedDeleteView,
    FeedListView,
    FeedUpdateView,
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
        "audio/<uuid:audio_uuid>/",
        ArticleMediaView.as_view(),
        name="article-media",
    ),
    # Feed management URLs
    path("feeds/", FeedListView.as_view(), name="feed-list"),
    path("feeds/new/", FeedCreateView.as_view(), name="feed-create"),
    path("feeds/<int:feed_id>/", FeedArticleListView.as_view(), name="feed-articles"),
    path(
        "feeds/<int:feed_id>/add/",
        FeedArticleCreateView.as_view(),
        name="feed-article-create",
    ),
    path("feeds/<int:feed_id>/edit/", FeedUpdateView.as_view(), name="feed-update"),
    path("feeds/<int:feed_id>/delete/", FeedDeleteView.as_view(), name="feed-delete"),
    # RSS feed URL (must come after management URLs to avoid conflicts)
    path("feeds/<uuid:token>/", UserFeed(), name="feed"),
    path("", HomeView.as_view(), name="home"),
]

# Serve media files in development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
