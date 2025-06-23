"""rss_tts URL Configuration."""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from text_to_audio.api_views import FeedArticleSubmitView
from text_to_audio.feeds import UserFeed
from text_to_audio.views import (
    ArticleCreateView,
    ArticleDeleteView,
    ArticleDetailView,
    ArticleListView,
    ArticleMediaView,
    FeedArticleCreateView,
    FeedArticleListView,
    FeedArticleStatusView,
    FeedCreateView,
    FeedDeleteView,
    FeedListView,
    FeedUpdateView,
    FollowedFeedCreateView,
    FollowedFeedDeleteView,
    FollowedFeedListView,
    FollowedFeedUpdateView,
    HomeView,
    RegenerateArticleView,
    SignUpView,
    article_voice_settings,
    voice_preferences,
    voice_preset_create,
    voice_preset_delete,
    voice_preset_edit,
    voice_preset_list,
)

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/login/", auth_views.LoginView.as_view(), name="login"),
    path("accounts/logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("accounts/signup/", SignUpView.as_view(), name="signup"),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="docs"),
    path("articles/", ArticleListView.as_view(), name="article-list"),
    path("articles/submit/", ArticleCreateView.as_view(), name="article-submit"),
    path(
        "articles/<int:article_id>/regenerate/",
        RegenerateArticleView.as_view(),
        name="article-regenerate",
    ),
    path(
        "articles/<int:article_id>/detail/",
        ArticleDetailView.as_view(),
        name="article-detail",
    ),
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
    path(
        "feeds/<int:feed_id>/articles/<int:article_id>/delete/",
        ArticleDeleteView.as_view(),
        name="article-delete",
    ),
    path(
        "feeds/<int:feed_id>/status/",
        FeedArticleStatusView.as_view(),
        name="feed-article-status",
    ),
    path("feeds/<int:feed_id>/edit/", FeedUpdateView.as_view(), name="feed-update"),
    path("feeds/<int:feed_id>/delete/", FeedDeleteView.as_view(), name="feed-delete"),
    # FollowedFeed management URLs
    path("followed-feeds/", FollowedFeedListView.as_view(), name="followedfeed-list"),
    path(
        "followed-feeds/new/",
        FollowedFeedCreateView.as_view(),
        name="followedfeed-create",
    ),
    path(
        "followed-feeds/<int:pk>/edit/",
        FollowedFeedUpdateView.as_view(),
        name="followedfeed-edit",
    ),
    path(
        "followed-feeds/<int:pk>/delete/",
        FollowedFeedDeleteView.as_view(),
        name="followedfeed-delete",
    ),
    path(
        "api/v1/feeds/<uuid:token>/articles/",
        FeedArticleSubmitView.as_view(),
        name="api-feed-article-submit",
    ),
    # RSS feed URL (must come after management URLs to avoid conflicts)
    path("feeds/<uuid:token>/", UserFeed(), name="feed"),
    # Voice preference URLs
    path("preferences/voice/", voice_preferences, name="voice_preferences"),
    path(
        "articles/<int:article_id>/voice/",
        article_voice_settings,
        name="article_voice_settings",
    ),
    # Voice preset URLs
    path("presets/voice/", voice_preset_list, name="voice_preset_list"),
    path("presets/voice/new/", voice_preset_create, name="voice_preset_create"),
    path(
        "presets/voice/<int:preset_id>/edit/",
        voice_preset_edit,
        name="voice_preset_edit",
    ),
    path(
        "presets/voice/<int:preset_id>/delete/",
        voice_preset_delete,
        name="voice_preset_delete",
    ),
    path("", HomeView.as_view(), name="home"),
]

# Serve media files in development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
