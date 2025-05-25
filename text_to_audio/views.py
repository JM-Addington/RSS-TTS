"""Views for the text_to_audio app.

This module defines the views used for the RSS-to-TTS system, handling article
submission, listing, media serving, and article deletion.
"""

import os
import uuid

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import FileResponse, HttpResponseNotFound, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.views import View
from django.views.generic import (
    CreateView,
    DeleteView,
    ListView,
    TemplateView,
    UpdateView,
)

from .forms import (
    ArticleSubmissionForm,
    ArticleVoiceForm,
    UserVoicePreferenceForm,
    VoicePresetForm,
)
from .models import Article, Feed, UserVoicePreset, UserVoiceProfile
from .services.user_preferences import UserPreferencesService
from .services.voice_configuration import VoiceConfigurationService
from .tasks import process_article
from .utils import extract_article_text, extract_title_from_html, fetch_url_content


class HomeView(TemplateView):
    """Basic home page view."""

    template_name = "index.html"


class ArticleCreateView(LoginRequiredMixin, CreateView):
    """View for submitting new articles (redirects to feed-based system)."""

    def get(self, request, *args, **kwargs):
        """Redirect to feed list for new feed-based system."""
        # Get or create default feed
        feed, _ = Feed.objects.get_or_create(user=request.user, name="Default")
        # Redirect to the feed-specific article creation
        return redirect("feed-article-create", feed_id=feed.pk)


class ArticleListView(LoginRequiredMixin, View):
    """View for listing all user's articles (redirects to feed list)."""

    def get(self, request, *args, **kwargs):
        """Redirect to feed list for new feed-based system."""
        return redirect("feed-list")


class ArticleMediaView(LoginRequiredMixin, View):
    """View for serving article media files."""

    def _find_by_pattern(self, article):
        """Try to find audio file by standard patterns and update article if found."""
        if not article.audio_uuid:
            return None

        # Try multiple locations for the audio file
        possible_paths = [
            # Check in MEDIA_ROOT/articles with new simplified structure
            os.path.join(
                settings.MEDIA_ROOT,
                "articles",
                f"{article.audio_uuid}.mp3",
            ),
            # Legacy paths for backwards compatibility
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

        # Path 5: Try simplified structure
        if article.audio_uuid:
            # New simplified path
            possible_paths.append(
                os.path.join(
                    settings.MEDIA_ROOT,
                    "articles",
                    f"{article.audio_uuid}.mp3",
                )
            )
            # Legacy paths for backwards compatibility
            user_id = (
                str(article.feed.user_id)
                if hasattr(article.feed, "user_id")
                else "unknown"
            )
            feed_id = str(article.feed.id) if hasattr(article.feed, "id") else "unknown"
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
                # Get user_id and feed_id for debugging
                feed_id = (
                    str(article.feed.id) if hasattr(article.feed, "id") else "unknown"
                )
                user_id = (
                    str(article.feed.user_id)
                    if hasattr(article.feed, "user_id")
                    else "unknown"
                )

                error_msg = (
                    f"Audio file not found. Details:\n"
                    f"- UUID: {article.audio_uuid}\n"
                    f"- Stored path: {article.audio_file_path}\n"
                    f"- Feed User ID: {user_id}\n"
                    f"- Feed ID: {feed_id}\n"
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


class FeedListView(LoginRequiredMixin, ListView):
    """View for listing a user's feeds."""

    model = Feed
    template_name = "feed_list.html"
    context_object_name = "feeds"

    def get_queryset(self):
        """Return only the user's feeds."""
        return Feed.objects.filter(user=self.request.user).order_by("-created_at")

    def get_context_data(self, **kwargs):
        """Add feed URLs and article counts to context."""
        context = super().get_context_data(**kwargs)

        # Add article count and RSS URL for each feed
        for feed in context["feeds"]:
            feed.article_count = feed.articles.count()

            # Generate RSS URL
            feed_path = reverse("feed", kwargs={"token": feed.token})
            if hasattr(settings, "SITE_URL"):
                feed.rss_url = f"{settings.SITE_URL.rstrip('/')}{feed_path}"
            else:
                request = self.request
                domain = request.get_host()
                protocol = "https" if request.is_secure() else "http"
                feed.rss_url = f"{protocol}://{domain}{feed_path}"

        return context


class FeedCreateView(LoginRequiredMixin, CreateView):
    """View for creating a new feed."""

    model = Feed
    fields = ["name"]
    template_name = "feed_form.html"

    def form_valid(self, form):
        """Set the user before saving."""
        form.instance.user = self.request.user
        return super().form_valid(form)

    def get_success_url(self):
        """Redirect to the new feed's article list."""
        # Use assert to help mypy understand self.object is not None
        assert self.object is not None
        return reverse_lazy("feed-articles", kwargs={"feed_id": self.object.pk})


class FeedUpdateView(LoginRequiredMixin, UpdateView):
    """View for updating a feed."""

    model = Feed
    fields = ["name"]
    template_name = "feed_form.html"
    pk_url_kwarg = "feed_id"

    def get_queryset(self):
        """Ensure users can only edit their own feeds."""
        return Feed.objects.filter(user=self.request.user)

    def get_success_url(self):
        """Redirect to the feed's article list."""
        return reverse_lazy("feed-articles", kwargs={"feed_id": self.object.pk})


class FeedDeleteView(LoginRequiredMixin, DeleteView):
    """View for deleting a feed."""

    model = Feed
    template_name = "feed_confirm_delete.html"
    success_url = reverse_lazy("feed-list")
    pk_url_kwarg = "feed_id"

    def get_queryset(self):
        """Ensure users can only delete their own feeds."""
        return Feed.objects.filter(user=self.request.user)


class FeedArticleListView(LoginRequiredMixin, ListView):
    """View for listing articles in a specific feed."""

    model = Article
    template_name = "article_list.html"
    context_object_name = "articles"

    def get_queryset(self):
        """Return only articles for the specified feed."""
        feed_id = self.kwargs.get("feed_id")
        return Article.objects.filter(
            feed__pk=feed_id, feed__user=self.request.user
        ).order_by("-created_at")

    def get_context_data(self, **kwargs):
        """Add feed information to context."""
        context = super().get_context_data(**kwargs)

        # Get the feed
        feed_id = self.kwargs.get("feed_id")
        feed = get_object_or_404(Feed, pk=feed_id, user=self.request.user)
        context["feed"] = feed

        # Generate RSS URL for this specific feed
        feed_path = reverse("feed", kwargs={"token": feed.token})
        if hasattr(settings, "SITE_URL"):
            context["feed_url"] = f"{settings.SITE_URL.rstrip('/')}{feed_path}"
        else:
            request = self.request
            domain = request.get_host()
            protocol = "https" if request.is_secure() else "http"
            context["feed_url"] = f"{protocol}://{domain}{feed_path}"

        return context


class FeedArticleCreateView(LoginRequiredMixin, CreateView):
    """View for submitting new articles to a specific feed."""

    form_class = ArticleSubmissionForm
    template_name = "article_form.html"

    def dispatch(self, request, *args, **kwargs):
        """Verify the feed exists and belongs to the user."""
        self.feed = get_object_or_404(
            Feed, pk=self.kwargs.get("feed_id"), user=request.user
        )
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        """Add user to form kwargs for preset access."""
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def form_valid(self, form):
        """Process the form and create the article for the specific feed."""
        article = form.save(commit=False)
        article.feed = self.feed

        # Handle voice preset if selected
        preset_id = form.cleaned_data.get("voice_preset")
        if preset_id:
            pref_service = UserPreferencesService()
            article = pref_service.save_article_preferences(
                article=article, voice_preset=preset_id
            )
        else:
            # Save direct voice and speed values if not using preset
            voice_id = form.cleaned_data.get("voice_id")
            speed = form.cleaned_data.get("speed")
            if voice_id:
                article.voice_id = voice_id
            if speed:
                article.speed = float(speed)

        # If URL is provided, validate it first
        if article.source_url:
            success, html, error = fetch_url_content(article.source_url)
            if not success:
                form.add_error("source_url", error)
                return self.form_invalid(form)

            # If no title provided but URL is valid, try to extract title
            if not article.title:
                title = extract_title_from_html(html)

                if not title:
                    success, content, _ = extract_article_text(html)
                    if success and content:
                        title = content[:100] + ("..." if len(content) > 100 else "")

                article.title = title or f"Article from {article.source_url}"

        article.save()
        task = process_article.delay(article.pk)
        article.celery_task_id = task.id
        # Restrict fields on save
        article.save(update_fields=["celery_task_id", "updated_at"])
        return super().form_valid(form)

    def get_success_url(self):
        """Redirect back to the feed's article list."""
        return reverse_lazy("feed-articles", kwargs={"feed_id": self.feed.pk})

    def get_context_data(self, **kwargs):
        """Add feed to context."""
        context = super().get_context_data(**kwargs)
        context["feed"] = self.feed
        return context


class RegenerateArticleView(LoginRequiredMixin, View):
    """View for regenerating an article's audio file."""

    def post(self, request, article_id):
        """Handle POST requests to regenerate an article.

        Creates a new article based on the existing one and queues it for processing.
        """
        # Get the original article
        original_article = get_object_or_404(
            Article, pk=article_id, feed__user=request.user
        )

        # Create a new article with the same content and voice
        new_article = Article(
            feed=original_article.feed,
            title=original_article.title,
            source_url=original_article.source_url,
            text_content=original_article.text_content,
            voice=original_article.voice,  # Preserve voice setting
            audio_uuid=uuid.uuid4(),  # Generate a new UUID
            status=Article.PROCESSING,
            # Copy voice settings
            voice_id=original_article.voice_id,
            speed=original_article.speed,
            voice_preset=original_article.voice_preset,
            detected_tone=original_article.detected_tone,
            summary=original_article.summary,
        )
        new_article.save()

        # Queue the new article for processing
        task = process_article.delay(new_article.pk)
        new_article.celery_task_id = task.id
        # Restrict fields on save
        new_article.save(update_fields=["celery_task_id", "updated_at"])

        # Get the feed ID
        # Using getattr to work around mypy limitations with Django models
        feed_id = getattr(original_article.feed, "pk", None)
        if feed_id is not None:
            return redirect("feed-articles", feed_id=feed_id)
        else:
            # Fallback - should not happen in normal operation
            return redirect("feed-list")


class ArticleDeleteView(LoginRequiredMixin, DeleteView):
    """View for deleting an article and its associated audio file."""

    model = Article
    template_name = "text_to_audio/article_confirm_delete.html"
    pk_url_kwarg = "article_id"

    def get_queryset(self):
        """Ensure users can only delete their own articles."""
        return Article.objects.filter(feed__user=self.request.user)

    def get_success_url(self):
        """Redirect to the article list of the feed."""
        # self.object is the deleted article instance
        return reverse_lazy("feed-articles", kwargs={"feed_id": self.object.feed.id})

    def _get_article_audio_file_path(self, article):
        """Find the audio file path for an article using various strategies."""
        file_path_to_delete = None

        # Attempt 1: Use _resolve_path logic if audio_file_path is set
        if article.audio_file_path:
            possible_paths = []
            # Docker path correction
            if article.audio_file_path.startswith("/app/"):
                path_suffix = article.audio_file_path.replace(
                    "/app/media/", ""
                ).replace("/app/", "")
                possible_paths.append(os.path.join(settings.BASE_DIR, path_suffix))

            # Relative path checks
            if not os.path.isabs(article.audio_file_path):
                possible_paths.append(
                    os.path.join(settings.MEDIA_ROOT, article.audio_file_path)
                )
                possible_paths.append(
                    os.path.join(settings.BASE_DIR, article.audio_file_path)
                )

            # Absolute path
            if os.path.isabs(article.audio_file_path):
                possible_paths.append(article.audio_file_path)

            for path in possible_paths:
                if os.path.exists(path):
                    file_path_to_delete = path
                    break
        # Attempt 2: Use _find_by_pattern logic if no path resolved or not set initially
        if not file_path_to_delete and article.audio_uuid:
            user_id = str(article.feed.user.id)
            feed_id_str = str(article.feed.id)
            article_storage_dir = getattr(
                settings,
                "ARTICLE_STORAGE_DIR",
                os.path.join(settings.BASE_DIR, "articles"),
            )

            possible_paths_pattern = [
                os.path.join(
                    article_storage_dir,
                    user_id,
                    feed_id_str,
                    f"article_{article.audio_uuid}.mp3",
                ),
                os.path.join(
                    settings.MEDIA_ROOT,
                    "articles",
                    user_id,
                    feed_id_str,
                    f"article_{article.audio_uuid}.mp3",
                ),
            ]
            for path in possible_paths_pattern:
                if os.path.exists(path):
                    file_path_to_delete = path
                    break
        return file_path_to_delete

    def delete(self, request, *args, **kwargs):
        """Delete the article and its associated audio file."""
        self.object = self.get_object()
        article = self.object

        # First find the file path using our helper method
        file_path_to_delete = self._get_article_audio_file_path(article)
        # Only try to delete if we found a path and the file exists
        if file_path_to_delete and os.path.exists(file_path_to_delete):
            try:
                # Force file deletion with os.unlink to ensure it happens
                os.unlink(file_path_to_delete)
                # Verify the file was deleted
                if os.path.exists(file_path_to_delete):
                    # If it still exists, try one more time with a different method
                    import shutil

                    dirname = os.path.dirname(file_path_to_delete)
                    shutil.rmtree(dirname, ignore_errors=True)
            except (OSError, FileNotFoundError, PermissionError) as e:
                # Log the error but continue with DB deletion
                import logging

                logger = logging.getLogger(__name__)
                logger.warning(f"Error deleting file {file_path_to_delete}: {e}")
                pass

        # Call delete method to remove DB record
        success_url = self.get_success_url()
        self.object.delete()
        return redirect(success_url)


class FeedArticleStatusView(LoginRequiredMixin, View):
    """Return JSON status for articles in a feed."""

    def get(self, request, feed_id):
        """Handle GET requests for article statuses."""
        feed = get_object_or_404(Feed, pk=feed_id, user=request.user)
        articles = Article.objects.filter(feed=feed).order_by("-created_at")

        data = [
            {
                "id": article.pk,
                "status": article.status,
                "audio_uuid": str(article.audio_uuid) if article.audio_uuid else "",
            }
            for article in articles
        ]

        return JsonResponse({"articles": data})


@login_required
def voice_preferences(request):
    """View for managing user voice preferences."""
    # Get or create profile
    profile, created = UserVoiceProfile.objects.get_or_create(user=request.user)

    # Get user presets
    pref_service = UserPreferencesService()
    presets = pref_service.get_user_presets(request.user)

    if request.method == "POST":
        form = UserVoicePreferenceForm(request.POST, instance=profile)
        if form.is_valid():
            form.save()
            messages.success(request, "Voice preferences updated successfully.")
            return redirect("voice_preferences")
    else:
        form = UserVoicePreferenceForm(instance=profile)

    return render(
        request,
        "text_to_audio/voice_preferences.html",
        {
            "form": form,
            "presets": presets,
        },
    )


@login_required
def voice_preset_list(request):
    """View for listing user's voice presets."""
    # Get user presets
    pref_service = UserPreferencesService()
    presets = pref_service.get_user_presets(request.user)

    return render(
        request,
        "text_to_audio/voice_preset_list.html",
        {
            "presets": presets,
        },
    )


@login_required
def voice_preset_create(request):
    """View for creating a new voice preset."""
    if request.method == "POST":
        form = VoicePresetForm(request.POST)
        if form.is_valid():
            # Create preset
            pref_service = UserPreferencesService()
            preset = pref_service.create_voice_preset(
                user=request.user,
                name=form.cleaned_data["name"],
                voice_id=form.cleaned_data["voice_id"],
                speed=form.cleaned_data["speed"],
                description=form.cleaned_data["description"],
            )

            messages.success(
                request, f'Voice preset "{preset.name}" created successfully.'
            )
            return redirect("voice_preset_list")
    else:
        form = VoicePresetForm()

    return render(
        request,
        "text_to_audio/voice_preset_form.html",
        {
            "form": form,
            "is_create": True,
        },
    )


@login_required
def voice_preset_edit(request, preset_id):
    """View for editing a voice preset."""
    # Get the preset
    preset = get_object_or_404(UserVoicePreset, id=preset_id, user=request.user)

    if request.method == "POST":
        form = VoicePresetForm(request.POST, instance=preset)
        if form.is_valid():
            # Update preset
            form.save()
            messages.success(
                request, f'Voice preset "{preset.name}" updated successfully.'
            )
            return redirect("voice_preset_list")
    else:
        form = VoicePresetForm(instance=preset)

    return render(
        request,
        "text_to_audio/voice_preset_form.html",
        {
            "form": form,
            "preset": preset,
            "is_create": False,
        },
    )


@login_required
def voice_preset_delete(request, preset_id):
    """View for deleting a voice preset."""
    # Get the preset
    preset = get_object_or_404(UserVoicePreset, id=preset_id, user=request.user)

    if request.method == "POST":
        # Delete preset
        pref_service = UserPreferencesService()
        pref_service.delete_voice_preset(preset_id)
        messages.success(request, f'Voice preset "{preset.name}" deleted successfully.')
        return redirect("voice_preset_list")

    return render(
        request,
        "text_to_audio/voice_preset_confirm_delete.html",
        {
            "preset": preset,
        },
    )


@login_required
def article_voice_settings(request, article_id):
    """View for managing article-specific voice settings."""
    article = get_object_or_404(Article, id=article_id, feed__user=request.user)

    if request.method == "POST":
        form = ArticleVoiceForm(request.POST, user=request.user)
        if form.is_valid():
            voice = form.cleaned_data.get("voice_id")
            speed = form.cleaned_data.get("speed")
            preset_id = form.cleaned_data.get("voice_preset")

            # Save preferences
            preferences = UserPreferencesService()

            if preset_id:
                # If preset selected, apply it
                preferences.save_article_preferences(
                    article=article, voice_preset=preset_id
                )
            else:
                # Otherwise save individual voice/speed settings
                preferences.save_article_preferences(
                    article=article,
                    voice=voice if voice else None,
                    speed=float(speed) if speed else None,
                )

            messages.success(request, "Article voice settings updated.")
            # Access the primary key in a type-safe way
            feed_id = (
                article.feed.pk
                if hasattr(article.feed, "pk")
                else getattr(article.feed, "id", None)
            )
            if feed_id is None:
                # Fallback to a default view if we can't get the feed ID
                return redirect("feed-list")
            return redirect("feed-articles", feed_id=feed_id)
    else:
        # Pre-fill form with current settings
        initial_data = {
            "voice_id": article.voice_id or "",
            "speed": article.speed or "",
            "voice_preset": article.voice_preset.id if article.voice_preset else "",
        }
        form = ArticleVoiceForm(initial=initial_data, user=request.user)

    return render(
        request,
        "text_to_audio/article_voice_settings.html",
        {"form": form, "article": article},
    )
