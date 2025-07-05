"""Views for the text_to_audio app.

This module defines the views used for the RSS-to-TTS system, handling article
submission, listing, media serving, and article deletion.
"""

import logging
import os
import uuid

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.models import User
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

from accounts.forms import CustomUserCreationForm

from .forms import (
    ArticleDetailForm,
    ArticleSubmissionForm,
    ArticleVoiceForm,
    FeedForm,
    FollowedFeedForm,
    UserVoicePreferenceForm,
    VoicePresetForm,
)
from .models import Article, Feed, FollowedFeed, UserVoicePreset, UserVoiceProfile
from .services.user_preferences import UserPreferencesService
from .services.voice_configuration import VoiceConfigurationService  # noqa: F401
from .tasks import process_article
from .utils import (
    extract_article_text,
    extract_text_from_pdf,
    extract_title_from_html,
    fetch_html_with_firecrawl,
    fetch_url_content,
    process_url_to_text,
    safe_delete_audio_file,
)

logger = logging.getLogger(__name__)


class HomeView(TemplateView):
    """Basic home page view."""

    template_name = "index.html"

    def dispatch(self, request, *args, **kwargs):
        """Redirect logged-in users to feeds page."""
        if request.user.is_authenticated:
            return redirect("feed-list")
        return super().dispatch(request, *args, **kwargs)


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


class ArticleMediaView(View):
    """View for serving article media files."""

    def _find_audio_file(self, article):
        """Find the audio file for an article using canonical path."""
        try:
            canonical_path = article.get_canonical_audio_path()
            if os.path.exists(canonical_path):
                return canonical_path
        except ValueError as e:
            logger.error(f"Cannot resolve canonical path for article {article.id}: {e}")
            return None
        except Exception as e:
            logger.error(
                f"Error resolving canonical path for article {article.id}: {e}"
            )
            return None

        return None

    def get(self, request, audio_uuid):
        """Serve the media file for an article by audio_uuid.

        This view can only be accessed by audio_uuid.
        """
        # Get the article by UUID (no authentication required - UUID provides security)
        article = get_object_or_404(
            Article,
            audio_uuid=audio_uuid,
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

        # Set Content-Type for development consistency (Caddy handles this in prod)
        response["Content-Type"] = "audio/mpeg"

        # Clean the filename for the Content-Disposition header
        safe_title = article.title.replace('"', "_").replace("/", "_")
        response["Content-Disposition"] = f'attachment; filename="{safe_title}.mp3"'

        return response


class SignUpView(CreateView):
    """View for registering a new user."""

    form_class = CustomUserCreationForm
    template_name = "registration/signup.html"
    success_url = reverse_lazy("login")

    def get(self, request, *args, **kwargs):
        """Redirect to login if users already exist."""
        from django.contrib.auth import get_user_model

        UserModel = get_user_model()
        if UserModel.objects.exists():
            return redirect("login")
        return super().get(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        """Redirect to login if users already exist."""
        from django.contrib.auth import get_user_model

        UserModel = get_user_model()
        if UserModel.objects.exists():
            return redirect("login")
        return super().post(request, *args, **kwargs)

    def form_valid(self, form):
        """Create new user and handle admin approval logic."""
        response = super().form_valid(form)
        user = self.object

        # AIDEV-NOTE: Custom User model handles first user logic automatically
        # The first user becomes super admin, others wait for approval

        # Refresh user to ensure profile is loaded
        user.refresh_from_db()

        # Show appropriate message based on user status
        if hasattr(user, "profile") and user.profile.is_super_admin:
            messages.success(
                self.request,
                "Welcome! You are the first user and have been granted admin privileges.",
            )
            # Create the user's first feed to improve onboarding experience
            Feed.objects.create(
                user=user, name="My Articles", voice_mode=Feed.VOICE_MODE_AUTO
            )
            logger.info(
                f"Created first feed 'My Articles' for new super admin {user.username}"
            )
        else:
            messages.info(
                self.request,
                "Your account has been created successfully. Please wait for an administrator to approve your account before you can log in.",
            )
            logger.info(f"New user {user.username} created, waiting for admin approval")

        return response


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
    form_class = FeedForm
    template_name = "feed_form.html"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

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
    form_class = FeedForm
    template_name = "feed_form.html"
    pk_url_kwarg = "feed_id"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

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


class FollowedFeedListView(LoginRequiredMixin, ListView):
    """View for listing a user's followed feeds."""

    model = FollowedFeed
    template_name = "text_to_audio/followedfeed_list.html"
    context_object_name = "followed_feeds"

    def get_queryset(self):
        """Return only the user's followed feeds."""
        return FollowedFeed.objects.filter(user=self.request.user).order_by(
            "-created_at"
        )


class FollowedFeedCreateView(LoginRequiredMixin, CreateView):
    """View for creating a new followed feed."""

    model = FollowedFeed
    form_class = FollowedFeedForm
    template_name = "text_to_audio/followedfeed_form.html"
    success_url = reverse_lazy("followedfeed-list")

    def get_form_kwargs(self):
        """Add user to form kwargs."""
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def form_valid(self, form):
        """Set the user before saving."""
        form.instance.user = self.request.user
        return super().form_valid(form)


class FollowedFeedUpdateView(LoginRequiredMixin, UpdateView):
    """View for updating a followed feed."""

    model = FollowedFeed
    form_class = FollowedFeedForm
    template_name = "text_to_audio/followedfeed_form.html"
    success_url = reverse_lazy("followedfeed-list")

    def get_form_kwargs(self):
        """Add user to form kwargs."""
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def get_queryset(self):
        """Ensure users can only edit their own followed feeds."""
        return FollowedFeed.objects.filter(user=self.request.user)


class FollowedFeedDeleteView(LoginRequiredMixin, DeleteView):
    """View for deleting a followed feed."""

    model = FollowedFeed
    template_name = "text_to_audio/followedfeed_confirm_delete.html"
    success_url = reverse_lazy("followedfeed-list")

    def get_queryset(self):
        """Ensure users can only delete their own followed feeds."""
        return FollowedFeed.objects.filter(user=self.request.user)


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

        # API submission URL for this feed
        api_path = reverse("api-feed-article-submit", kwargs={"token": feed.token})
        if hasattr(settings, "SITE_URL"):
            context["api_url"] = f"{settings.SITE_URL.rstrip('/')}{api_path}"
        else:
            request = self.request
            domain = request.get_host()
            protocol = "https" if request.is_secure() else "http"
            context["api_url"] = f"{protocol}://{domain}{api_path}"

        return context


class FeedArticleCreateView(LoginRequiredMixin, CreateView):
    """View for submitting new articles to a specific feed."""

    form_class = ArticleSubmissionForm
    template_name = "article_form.html"

    def dispatch(self, request, *args, **kwargs):
        """Verify the feed exists and belongs to the user."""
        # LoginRequiredMixin should handle this, but add extra safety check
        if not request.user.is_authenticated:
            return self.handle_no_permission()

        self.feed = get_object_or_404(
            Feed, pk=self.kwargs.get("feed_id"), user=request.user
        )
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        """Add user to form kwargs for preset access."""
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        if self.feed.default_voice_preset:
            kwargs.setdefault("initial", {})[
                "voice_preset"
            ] = self.feed.default_voice_preset.id
        return kwargs

    def form_valid(self, form):
        """Process the form and create the article for the specific feed."""
        article = form.save(commit=False)
        article.feed = self.feed

        # Handle voice preset if selected
        preset_id = form.cleaned_data.get("voice_preset")
        if preset_id:
            try:
                preset = UserVoicePreset.objects.get(id=preset_id)
                article.voice_preset = preset
                from text_to_audio.models import VOICE_CHOICES

                standard_voices = [choice[0] for choice in VOICE_CHOICES]
                if preset.voice_id in standard_voices:
                    article.voice = preset.voice_id
                    article.voice_id = None
                else:
                    article.voice_id = preset.voice_id
                    article.voice = "alloy"
                article.speed = preset.speed
            except UserVoicePreset.DoesNotExist:
                pass
        elif self.feed.default_voice_preset:
            preset = self.feed.default_voice_preset
            article.voice_preset = preset
            from text_to_audio.models import VOICE_CHOICES

            standard_voices = [choice[0] for choice in VOICE_CHOICES]
            if preset.voice_id in standard_voices:
                article.voice = preset.voice_id
                article.voice_id = None
            else:
                article.voice_id = preset.voice_id
                article.voice = "alloy"
            article.speed = preset.speed
        else:
            voice_id = form.cleaned_data.get("voice_id")
            speed = form.cleaned_data.get("speed")
            if voice_id:
                from text_to_audio.models import VOICE_CHOICES

                standard_voices = [choice[0] for choice in VOICE_CHOICES]
                if voice_id in standard_voices:
                    article.voice = voice_id
                    article.voice_id = None
                else:
                    article.voice_id = voice_id
                    article.voice = "alloy"
            if speed:
                article.speed = float(speed)

        document_file = form.cleaned_data.get("document_file")

        if document_file:
            filename = document_file.name
            file_ext = os.path.splitext(filename)[1].lower()
            content_type = document_file.content_type
            extracted_text = None

            # Validate using content_type for consistency with form validation
            if content_type == "application/pdf":
                extracted_text = extract_text_from_pdf(document_file)
                if extracted_text.startswith("Error: Could not extract text from PDF"):
                    form.add_error(
                        "document_file",
                        "Unable to extract text from the PDF file. The file might be password-protected, "
                        "corrupted, or contain only scanned images without text layers. "
                        "Try using a different PDF or extract the text manually.",
                    )
                    return self.form_invalid(form)
            elif content_type == "text/html":
                try:
                    document_file.seek(0)  # Reset file pointer to beginning
                    html_content = document_file.read().decode("utf-8")
                    success, text, error = extract_article_text(html_content)
                    if not success:
                        form.add_error(
                            "document_file",
                            f"Unable to extract content from the HTML file: {error or 'No content found'}. "
                            "The file might be malformed or contain no meaningful content. "
                            "Try using a different HTML file or extract the text manually.",
                        )
                        return self.form_invalid(form)
                    extracted_text = text
                except UnicodeDecodeError:
                    form.add_error(
                        "document_file",
                        "Unable to decode the HTML file. The file might use an unsupported encoding. "
                        "Try saving the file as UTF-8 and uploading again.",
                    )
                    return self.form_invalid(form)
            else:
                # This case should ideally be caught by form validation, but as a fallback:
                form.add_error(
                    "document_file",
                    f"Unsupported file type: {content_type}. Only PDF and HTML files are supported.",
                )
                return self.form_invalid(form)

            article.text_content = extracted_text
            if not article.title:
                # Extract title from HTML content if available
                if content_type == "text/html":
                    # Use html_content variable that should be available from earlier processing
                    # or try to re-read the file if needed
                    html_for_title = None

                    if "html_content" in locals() and html_content:
                        # Use the html_content we already have
                        html_for_title = html_content
                    else:
                        # Need to read the HTML content again
                        try:
                            document_file.seek(0)  # Reset file pointer to beginning
                            html_for_title = document_file.read().decode("utf-8")
                        except Exception as e:
                            logger.error(
                                f"Error reading HTML file for title extraction: {e}"
                            )

                    # Extract the title if we have HTML content
                    if html_for_title:
                        extracted_title = extract_title_from_html(html_for_title)
                        if extracted_title:
                            article.title = extracted_title

                # If still no title, use filename
                if not article.title:
                    article.title = os.path.splitext(filename)[0]

        elif article.source_url:  # Process URL only if no document is uploaded
            # Use process_url_to_text to get both HTML and text with Firecrawl fallback support
            url_success, url_text, url_error = process_url_to_text(article.source_url)
            if not url_success:
                form.add_error("source_url", url_error)
                return self.form_invalid(form)

            # We need HTML for title extraction, so fetch it separately if needed
            # Since process_url_to_text returns text, we may need HTML for title extraction
            success, html, error = fetch_url_content(article.source_url)
            if not success:
                # If regular fetch fails, try Firecrawl for HTML
                from django.conf import settings

                api_key = getattr(settings, "FIRECRAWL_API_KEY", None)
                if api_key and any(code in error for code in ["404", "403", "400"]):
                    fc_success, html, fc_error = fetch_html_with_firecrawl(
                        article.source_url
                    )
                    if not fc_success:
                        # If both fail, we still have the text from process_url_to_text
                        html = f"<html><body><p>{url_text}</p></body></html>"
                else:
                    # If no API key or different error, create basic HTML from text
                    html = f"<html><body><p>{url_text}</p></body></html>"

            if not article.title:
                title = extract_title_from_html(html)
                if not title:
                    # Try to get some text from the page for a title
                    url_text_success, url_page_text, _ = extract_article_text(html)

                    if url_text_success and url_page_text:
                        # Get first 100 chars of content for a title
                        first_paragraph = (
                            url_page_text.split("\n")[0]
                            if "\n" in url_page_text
                            else url_page_text
                        )
                        title = first_paragraph[:100] + (
                            "..." if len(first_paragraph) > 100 else ""
                        )

                    # Check URL for a possible title if text extraction failed
                    if not title:
                        # Try to get a title from the last part of the URL
                        from urllib.parse import urlparse

                        path = urlparse(article.source_url).path
                        path_parts = [p for p in path.split("/") if p]

                        if path_parts:
                            # Use the last meaningful part of the URL
                            url_title = (
                                path_parts[-1].replace("-", " ").replace("_", " ")
                            )
                            # Remove file extensions if present
                            url_title = (
                                url_title.split(".")[0]
                                if "." in url_title
                                else url_title
                            )
                            if url_title:
                                title = url_title.capitalize()

                article.title = title or f"Article from {article.source_url}"
            # If text_content is still empty (e.g. not file upload, and no direct text input)
            # then use the text we already extracted from process_url_to_text
            if not article.text_content:
                article.text_content = url_text

        article.save()
        task = process_article.delay(article.pk)
        article.celery_task_id = task.id
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
            audio_uuid=uuid.uuid4(),  # Generate a new UUID
            status=Article.PROCESSING,
            # Copy voice settings using single source of truth
            voice_id=original_article.voice_id,
            voice=original_article.voice,  # Use the same voice field as original
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


class ArticleDetailView(LoginRequiredMixin, View):
    """View to display and edit details of a generated article."""

    template_name = "text_to_audio/article_detail.html"

    def get(self, request, article_id):
        """Render the detail form with the article's data."""
        article = get_object_or_404(Article, pk=article_id, feed__user=request.user)
        form = ArticleDetailForm(instance=article)
        return render(request, self.template_name, {"form": form, "article": article})

    def post(self, request, article_id):
        """Create a new article based on submitted data."""
        original = get_object_or_404(Article, pk=article_id, feed__user=request.user)
        form = ArticleDetailForm(request.POST)
        if form.is_valid():
            new_article = Article(
                feed=original.feed,
                title=form.cleaned_data["title"],
                source_url=original.source_url,
                text_content=form.cleaned_data["text_content"],
                summary=form.cleaned_data.get("summary"),
                speed=(
                    float(form.cleaned_data.get("speed"))
                    if form.cleaned_data.get("speed")
                    else None
                ),
                audio_uuid=uuid.uuid4(),
                status=Article.PROCESSING,
            )

            # Apply single source of truth for voice fields
            voice_id = form.cleaned_data.get("voice_id")
            if voice_id:
                from text_to_audio.models import VOICE_CHOICES

                standard_voices = [choice[0] for choice in VOICE_CHOICES]

                if voice_id in standard_voices:
                    new_article.voice = voice_id
                    new_article.voice_id = None
                else:
                    new_article.voice_id = voice_id
                    new_article.voice = (
                        "alloy"  # Reset to default for validation compatibility
                    )
            new_article.save()
            task = process_article.delay(new_article.pk)
            new_article.celery_task_id = task.id
            new_article.save(update_fields=["celery_task_id", "updated_at"])
            return redirect("feed-articles", feed_id=original.feed.pk)

        return render(request, self.template_name, {"form": form, "article": original})


class ArticleDeleteView(LoginRequiredMixin, DeleteView):
    """View for deleting an article and its associated audio file."""

    model = Article
    template_name = "text_to_audio/article_confirm_delete.html"
    pk_url_kwarg = "article_id"

    def get_queryset(self):
        """Ensure users can only delete their own articles."""
        return Article.objects.filter(feed__user=self.request.user)

    def dispatch(self, request, *args, **kwargs):
        """Override dispatch to check for article ownership early."""
        from django.http import Http404
        from django.shortcuts import get_object_or_404

        # Get the article_id from URL kwargs
        article_id = kwargs.get("article_id")
        if article_id:
            # Check if the article exists and belongs to the current user
            try:
                get_object_or_404(Article, pk=article_id, feed__user=request.user)
            except Exception:
                raise Http404("Article not found or access denied")

        return super().dispatch(request, *args, **kwargs)

    def get_success_url(self):
        """Redirect to the article list of the feed."""
        # self.object is the deleted article instance
        return reverse_lazy("feed-articles", kwargs={"feed_id": self.object.feed.id})

    def _get_article_audio_file_path(self, article):
        """Find the audio file path for an article using canonical path."""
        try:
            canonical_path = article.get_canonical_audio_path()
            if os.path.exists(canonical_path):
                return canonical_path
        except ValueError as e:
            logger.error(f"Cannot resolve canonical path for article {article.id}: {e}")
        except Exception as e:
            logger.error(
                f"Error resolving canonical path for article {article.id}: {e}"
            )

        return None

    def delete(self, request, *args, **kwargs):
        """Delete the article and its associated audio file."""
        self.object = self.get_object()
        article = self.object

        # First find the file path using our helper method
        file_path_to_delete = self._get_article_audio_file_path(article)
        # Only try to delete if we found a path
        if file_path_to_delete:
            try:
                # Use safe deletion function with directory protection
                safe_delete_audio_file(file_path_to_delete)
            except AssertionError as e:
                # Log assertion errors (like trying to delete directory) but continue
                logger.error(
                    f"Safe deletion assertion failed for {file_path_to_delete}: {e}"
                )
            except Exception as e:
                # Log any other unexpected errors but continue with DB deletion
                logger.warning(
                    f"Unexpected error during safe deletion of {file_path_to_delete}: {e}"
                )

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
