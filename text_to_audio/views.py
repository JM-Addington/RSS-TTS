"""Views for the text_to_audio app.

This module defines the views used for the RSS-to-TTS system, handling article
submission, listing, and media serving.
"""

import os

from django.conf import settings
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import FileResponse, HttpResponseNotFound
from django.shortcuts import get_object_or_404
from django.urls import reverse, reverse_lazy
from django.views import View
from django.views.generic import CreateView, ListView, TemplateView

from .forms import ArticleSubmissionForm
from .models import Article, Feed
from .tasks import process_article
from .utils import extract_article_text, extract_title_from_html, fetch_url_content


class HomeView(TemplateView):
    """Basic home page view."""

    template_name = "index.html"


class ArticleCreateView(LoginRequiredMixin, CreateView):
    """View for submitting new articles."""

    form_class = ArticleSubmissionForm
    template_name = "article_form.html"
    success_url = reverse_lazy("article-list")

    def form_valid(self, form):
        """Process the form and create the article.

        Creates a default feed for the user if none exists, saves the article
        to the database, and schedules the article for processing.
        If no title is provided but a URL is, extracts title from the page.
        Validates URL accessibility before submission.
        """
        feed, _ = Feed.objects.get_or_create(user=self.request.user, name="Default")
        article = form.save(commit=False)
        article.feed = feed

        # If URL is provided, validate it first
        if article.source_url:
            success, html, error = fetch_url_content(article.source_url)
            if not success:
                # Add the error to the form for user-friendly display
                form.add_error("source_url", error)
                return self.form_invalid(form)

            # If no title provided but URL is valid, try to extract title
            if not article.title:
                # Try to extract title from HTML
                title = extract_title_from_html(html)

                # If no title found, use first 100 chars of content
                if not title:
                    success, content, _ = extract_article_text(html)
                    if success and content:
                        title = content[:100] + ("..." if len(content) > 100 else "")

                article.title = title or f"Article from {article.source_url}"

        article.save()
        process_article.delay(article.id)
        return super().form_valid(form)


class ArticleListView(LoginRequiredMixin, ListView):
    """View for listing a user's articles."""

    model = Article
    template_name = "article_list.html"
    context_object_name = "articles"

    def get_queryset(self):
        """Return only the user's articles."""
        user = self.request.user
        return Article.objects.filter(feed__user=user).order_by("-created_at")

    def get_context_data(self, **kwargs):
        """Add feed URL to context."""
        context = super().get_context_data(**kwargs)

        # Get the user's default feed
        feed = Feed.objects.filter(user=self.request.user).first()

        if feed:
            feed_path = reverse("feed", kwargs={"token": feed.token})

            # Use SITE_URL from settings if available
            if hasattr(settings, "SITE_URL"):
                feed_url = f"{settings.SITE_URL.rstrip('/')}{feed_path}"
            else:
                # Fallback to request host
                request = self.request
                domain = request.get_host()
                protocol = "https" if request.is_secure() else "http"
                feed_url = f"{protocol}://{domain}{feed_path}"

            context["feed_url"] = feed_url

        return context


class ArticleMediaView(LoginRequiredMixin, View):
    """View for serving article media files."""

    def _find_by_pattern(self, article):
        """Try to find audio file by standard patterns and update article if found."""
        if not article.audio_uuid:
            return None

        # Try multiple locations for the audio file
        possible_paths = [
            # Check in ARTICLE_STORAGE_DIR (BASE_DIR/articles)
            os.path.join(
                getattr(
                    settings,
                    "ARTICLE_STORAGE_DIR",
                    os.path.join(settings.BASE_DIR, "articles"),
                ),
                str(article.feed.user.id),
                str(article.feed.id),
                f"article_{article.audio_uuid}.mp3",
            ),
            # Check in MEDIA_ROOT/articles
            os.path.join(
                settings.MEDIA_ROOT,
                "articles",
                str(article.feed.user.id),
                str(article.feed.id),
                f"article_{article.audio_uuid}.mp3",
            ),
        ]

        for path in possible_paths:
            if os.path.exists(path):
                # Store relative to MEDIA_ROOT for consistency with tasks.py
                try:
                    relative_path = os.path.relpath(path, settings.MEDIA_ROOT)
                    article.audio_file_path = relative_path
                    article.status = Article.COMPLETED
                    article.save(update_fields=["audio_file_path", "status"])
                    return path
                except ValueError:
                    # If path is not relative to MEDIA_ROOT, store as absolute path
                    article.audio_file_path = path
                    article.status = Article.COMPLETED
                    article.save(update_fields=["audio_file_path", "status"])
                    return path

        return None

    def _resolve_path(self, article):
        """Resolve the audio file path based on different storage strategies."""
        # Try multiple path resolution strategies
        possible_paths = []

        # Path 1: Check if it's a Docker path
        if article.audio_file_path.startswith("/app/"):
            # Docker path correction
            path_suffix = article.audio_file_path.replace("/app/media/", "").replace(
                "/app/", ""
            )
            possible_paths.append(os.path.join(settings.BASE_DIR, path_suffix))

        # Path 2: If it's a relative path, try with MEDIA_ROOT first
        if not os.path.isabs(article.audio_file_path):
            path = os.path.join(settings.MEDIA_ROOT, article.audio_file_path)
            possible_paths.append(path)

        # Path 3: Try with BASE_DIR (for backwards compatibility)
        if not os.path.isabs(article.audio_file_path):
            possible_paths.append(
                os.path.join(settings.BASE_DIR, article.audio_file_path)
            )

        # Path 4: If it's an absolute path, use it directly
        if os.path.isabs(article.audio_file_path):
            possible_paths.append(article.audio_file_path)

        # Path 5: Try with ARTICLE_STORAGE_DIR
        article_storage_dir = getattr(
            settings, "ARTICLE_STORAGE_DIR", os.path.join(settings.BASE_DIR, "articles")
        )
        if article.audio_uuid:
            # Construct a path using the UUID
            user_id = article.feed.user.id
            feed_id = article.feed.id
            possible_paths.append(
                os.path.join(
                    article_storage_dir,
                    str(user_id),
                    str(feed_id),
                    f"article_{article.audio_uuid}.mp3",
                )
            )
            # Also try in MEDIA_ROOT
            possible_paths.append(
                os.path.join(
                    settings.MEDIA_ROOT,
                    "articles",
                    str(user_id),
                    str(feed_id),
                    f"article_{article.audio_uuid}.mp3",
                )
            )

        # Check all possible paths
        for path in possible_paths:
            if os.path.exists(path):
                return path

        # If we get here, we couldn't find the file
        return None

    def _find_audio_file(self, article):
        """Find the audio file for an article using various path strategies."""
        # Case 1: No path set, try to find by pattern
        if not article.audio_file_path:
            return self._find_by_pattern(article)

        # Case 2: Path set, try to resolve it
        file_path = self._resolve_path(article)
        if file_path:
            return file_path

        # Case 3: Last resort, try to find by pattern again
        return self._find_by_pattern(article)

    def get(self, request, audio_uuid):
        """Serve the media file for an article by audio_uuid.

        This view can only be accessed by audio_uuid.
        """
        # Get the article by UUID
        article = get_object_or_404(
            Article,
            audio_uuid=audio_uuid,
            feed__user=request.user,
            status=Article.COMPLETED,
        )

        if not article.audio_file_path:
            return HttpResponseNotFound("Audio file not available")

        file_path = self._find_audio_file(article)
        if not file_path:
            # Add debug information to help diagnose issues
            if settings.DEBUG:
                error_msg = (
                    f"Audio file not found. Details:\n"
                    f"- UUID: {article.audio_uuid}\n"
                    f"- Stored path: {article.audio_file_path}\n"
                    f"- Feed User: {article.feed.user}\n"
                    f"- Feed ID: {article.feed.id}\n"
                    f"- MEDIA_ROOT: {settings.MEDIA_ROOT}\n"
                    f"- BASE_DIR: {settings.BASE_DIR}"
                )
                return HttpResponseNotFound(error_msg)
            else:
                return HttpResponseNotFound("Audio file not found")

        # Serve the file
        response = FileResponse(open(file_path, "rb"))

        # Clean the filename for the Content-Disposition header
        safe_title = article.title.replace('"', "_").replace("/", "_")
        response["Content-Disposition"] = f'attachment; filename="{safe_title}.mp3"'

        return response


class SignUpView(CreateView):
    """View for registering a new user."""

    form_class = UserCreationForm
    template_name = "registration/signup.html"
    success_url = reverse_lazy("login")
