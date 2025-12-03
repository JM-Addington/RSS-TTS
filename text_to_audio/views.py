"""Views for the text_to_audio app.

This module defines the views used for the RSS-to-TTS system, handling article
submission, listing, media serving, and article deletion.
"""

import logging
import os
import tempfile
import uuid

import openai
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.models import User
from django.http import (
    FileResponse,
    HttpResponseBadRequest,
    HttpResponseNotFound,
    JsonResponse,
)
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
from appconfig.utils import get_site_url

from .forms import (
    ArticleDetailForm,
    ArticleSubmissionForm,
    ArticleVoiceForm,
    FeedForm,
    FollowedFeedForm,
    UserVoicePreferenceForm,
    VoicePresetForm,
    VoiceSampleForm,
)
from .models import (
    Article,
    Feed,
    FollowedFeed,
    OpenAIUsageStats,
    UserVoicePreset,
    UserVoiceProfile,
)
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
                "Your account has been created successfully. Please wait for an "
                "administrator to approve your account before you can log in.",
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
        """Add feed URLs, article counts, and total audio duration to context."""
        from django.db.models import Sum

        context = super().get_context_data(**kwargs)

        # Add article count, total audio duration, and RSS URL for each feed
        for feed in context["feeds"]:
            feed.article_count = feed.articles.count()

            # Calculate total audio duration for completed articles (in seconds)
            total_duration = feed.articles.filter(
                status="COMPLETED", audio_duration__isnull=False
            ).aggregate(total=Sum("audio_duration"))["total"]
            feed.total_audio_duration = total_duration or 0

            # Generate RSS URL
            feed_path = reverse("feed", kwargs={"token": feed.token})
            if get_site_url():
                feed.rss_url = f"{get_site_url().rstrip('/')}{feed_path}"
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


class GenerateFeedEmailView(LoginRequiredMixin, View):
    """View for generating an email address for a feed."""

    def post(self, request, feed_id):
        """Handle POST requests to generate an email address for a feed.

        Args:
            request: The HTTP request object
            feed_id: The ID of the feed

        Returns:
            Redirect to the feed list or article list
        """
        # Get the feed (must be owned by current user)
        feed = get_object_or_404(Feed, pk=feed_id, user=request.user)

        logger.info(
            f"User {request.user.username} requested email generation for feed {feed.id} ({feed.name})"
        )

        # Check if feed already has an email
        if feed.inbound_email:
            logger.warning(
                f"Feed {feed.id} ({feed.name}) already has email: {feed.inbound_email}"
            )
            messages.info(
                request,
                f"Feed '{feed.name}' already has an email address: {feed.inbound_email}",
            )
            # Check where the request came from
            redirect_to = request.POST.get("redirect", "feed-list")
            if redirect_to == "feed-articles":
                return redirect("feed-articles", feed_id=feed_id)
            return redirect("feed-list")

        # Check if Mailgun is configured
        if not settings.MAILGUN_API_KEY or not settings.MAILGUN_DOMAIN:
            logger.error(
                f"Mailgun not configured - cannot generate email for feed {feed.id} ({feed.name})"
            )
            messages.error(
                request,
                "Mailgun is not configured. Please contact the administrator.",
            )
            redirect_to = request.POST.get("redirect", "feed-list")
            if redirect_to == "feed-articles":
                return redirect("feed-articles", feed_id=feed_id)
            return redirect("feed-list")

        # Generate email address
        email_address = feed.generate_inbound_email()
        if not email_address:
            logger.error(
                f"Failed to generate email address for feed {feed.id} ({feed.name})"
            )
            messages.error(
                request,
                f"Failed to generate email address for feed '{feed.name}'.",
            )
            redirect_to = request.POST.get("redirect", "feed-list")
            if redirect_to == "feed-articles":
                return redirect("feed-articles", feed_id=feed_id)
            return redirect("feed-list")

        # Try to create Mailgun route
        site_url = getattr(settings, "SITE_URL", None)
        if site_url:
            webhook_url = f"{site_url.rstrip('/')}/api/v1/mailgun/incoming/"

            from .services.mailgun_service import MailgunService

            mailgun_service = MailgunService()
            success, route_id, error = mailgun_service.create_route(
                feed_email=email_address,
                webhook_url=webhook_url,
                description=f"Route for feed: {feed.name} (ID: {feed.id})",
            )

            if success and route_id:
                # Save email and route ID
                feed.inbound_email = email_address
                feed.mailgun_route_id = route_id
                feed.save(update_fields=["inbound_email", "mailgun_route_id"])
                logger.info(
                    f"Successfully created email {email_address} and route {route_id} "
                    f"for feed {feed.id} ({feed.name}) by user {request.user.username}"
                )
                messages.success(
                    request,
                    f"Successfully created email address: {email_address}",
                )
            else:
                # Save just the email address
                feed.inbound_email = email_address
                feed.save(update_fields=["inbound_email"])
                logger.warning(
                    f"Created email {email_address} for feed {feed.id} ({feed.name}) "
                    f"but failed to create Mailgun route: {error}"
                )
                messages.warning(
                    request,
                    f"Created email address {email_address}, but failed to create "
                    f"Mailgun route. You may need to create the route manually.",
                )
        else:
            # No SITE_URL - just save the email
            feed.inbound_email = email_address
            feed.save(update_fields=["inbound_email"])
            logger.warning(
                f"Created email {email_address} for feed {feed.id} ({feed.name}) "
                f"but SITE_URL not configured - route not created"
            )
            messages.warning(
                request,
                f"Created email address {email_address}, but SITE_URL is not configured. "
                f"Mailgun route must be created manually.",
            )

        # Redirect back to where the user came from
        redirect_to = request.POST.get("redirect", "feed-list")
        if redirect_to == "feed-articles":
            return redirect("feed-articles", feed_id=feed_id)
        return redirect("feed-list")


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
        if get_site_url():
            context["feed_url"] = f"{get_site_url().rstrip('/')}{feed_path}"
        else:
            request = self.request
            domain = request.get_host()
            protocol = "https" if request.is_secure() else "http"
            context["feed_url"] = f"{protocol}://{domain}{feed_path}"

        # API submission URL for this feed
        api_path = reverse("api-feed-article-submit", kwargs={"token": feed.token})
        if get_site_url():
            context["api_url"] = f"{get_site_url().rstrip('/')}{api_path}"
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
                    # Clean HTML to remove unwanted elements (same as URL processing)
                    from .utils import clean_html_minimal

                    cleaned_html = clean_html_minimal(html_content)
                    success, text, error = extract_article_text(cleaned_html)
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
            # AIDEV-NOTE: Plaintext and markdown - read content directly, no extraction needed
            elif content_type in ["text/plain", "text/markdown", "text/x-markdown"]:
                try:
                    document_file.seek(0)  # Reset file pointer to beginning
                    extracted_text = document_file.read().decode("utf-8")
                    if not extracted_text.strip():
                        form.add_error(
                            "document_file",
                            "The file appears to be empty. Please upload a file with content.",
                        )
                        return self.form_invalid(form)
                except UnicodeDecodeError:
                    form.add_error(
                        "document_file",
                        "Unable to decode the file. The file might use an unsupported encoding. "
                        "Try saving the file as UTF-8 and uploading again.",
                    )
                    return self.form_invalid(form)
            else:
                # This case should ideally be caught by form validation, but as a fallback:
                form.add_error(
                    "document_file",
                    f"Unsupported file type: {content_type}. Only PDF, HTML, TXT, and Markdown files are supported.",
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
                from appconfig.utils import get_firecrawl_api_key

                api_key = get_firecrawl_api_key()
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
def voice_preset_test(request, preset_id=None):
    """Generate a real-time voice sample with current form values."""
    if (
        request.method != "POST"
        or request.headers.get("X-Requested-With") != "XMLHttpRequest"
    ):
        return HttpResponseBadRequest("Invalid request")

    # Get form data
    voice_id = request.POST.get("voice_id")
    speed = request.POST.get("speed")
    text = request.POST.get("text", "").strip()
    prompt = request.POST.get("prompt", "").strip()

    # Validate inputs
    if not voice_id or not speed or not text:
        return HttpResponseBadRequest("Missing required fields")

    try:
        speed = float(speed)
        if speed < 0.25 or speed > 4.0:
            return HttpResponseBadRequest("Speed must be between 0.25 and 4.0")
    except (ValueError, TypeError):
        return HttpResponseBadRequest("Invalid speed value")

    # Limit text length
    words = text.split()
    if len(words) > 100:
        return HttpResponseBadRequest("Text must be 100 words or fewer")
    text = " ".join(words[:100])

    # If preset_id is provided, verify user owns it
    if preset_id:
        get_object_or_404(UserVoicePreset, id=preset_id, user=request.user)

    try:
        # AIDEV-NOTE: Use TTSService for provider abstraction (supports OpenAI and Google TTS)
        # Detect provider from voice_id
        provider = "google" if voice_id.startswith("en-US-") else "openai"

        from text_to_audio.services.tts_service import TTSService

        tts_service = TTSService(provider=provider)

        logger.info(
            f"Voice test: provider={provider}, voice={voice_id}, speed={speed}, "
            f"prompt={'yes' if prompt else 'no'}"
        )

        audio_data = tts_service.generate_speech(
            text=text,
            voice=voice_id,
            speed=speed,
            instructions=prompt if prompt else None,
            response_format="mp3",
        )

        from io import BytesIO

        audio_file = BytesIO(audio_data)
        response = FileResponse(audio_file, content_type="audio/mpeg")
        response["Content-Disposition"] = 'inline; filename="voice_test.mp3"'  # type: ignore[index]
        response["Cache-Control"] = "no-cache"  # type: ignore[index]
        return response

    except Exception as e:
        logger.error(f"Error generating voice sample: {e}")
        return HttpResponseBadRequest("Error generating voice sample")


@login_required
def voice_preset_sample(request, preset_id):
    """Generate an audio sample for a voice preset."""
    preset = get_object_or_404(UserVoicePreset, id=preset_id, user=request.user)

    if request.method == "POST":
        form = VoiceSampleForm(request.POST)
        if form.is_valid():
            text = form.cleaned_data["text"]

            try:
                # AIDEV-NOTE: Use TTSService for provider abstraction (supports OpenAI and Google TTS)
                # Detect provider from voice_id
                provider = (
                    "google" if preset.voice_id.startswith("en-US-") else "openai"
                )

                from text_to_audio.services.tts_service import TTSService

                tts_service = TTSService(provider=provider)

                logger.info(
                    f"Voice preset sample: provider={provider}, voice={preset.voice_id}, "
                    f"speed={preset.speed}"
                )

                audio_data = tts_service.generate_speech(
                    text=text,
                    voice=preset.voice_id,
                    speed=preset.speed,
                    instructions=preset.prompt if preset.prompt else None,
                    response_format="mp3",
                )

                from io import BytesIO

                audio_file = BytesIO(audio_data)
                response = FileResponse(audio_file, content_type="audio/mpeg")
                response["Content-Disposition"] = (  # type: ignore[index]
                    'inline; filename="voice_sample.mp3"'
                )
                return response

            except Exception as e:
                logger.error(f"Error generating voice sample: {e}")
                # Handle AJAX errors
                if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                    return HttpResponseBadRequest(
                        "Error generating voice sample. Please try again."
                    )
                else:
                    # For regular form submission, add error to form
                    form.add_error(
                        None, "Error generating voice sample. Please try again."
                    )
        else:
            # Handle AJAX form validation errors
            if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                errors = []
                for field, field_errors in form.errors.items():
                    for error in field_errors:
                        errors.append(f"{field}: {error}")
                return HttpResponseBadRequest("; ".join(errors))
    else:
        form = VoiceSampleForm()

    return render(
        request,
        "text_to_audio/voice_sample_form.html",
        {"form": form, "preset": preset},
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
            tts_provider = form.cleaned_data.get("tts_provider")

            # Save TTS provider if specified
            if tts_provider:
                article.tts_provider = tts_provider
                article.save(update_fields=["tts_provider"])

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
        # Voice can be in either article.voice or article.voice_id depending on whether it's standard or custom
        current_voice = article.voice_id if article.voice_id else article.voice
        initial_data = {
            "tts_provider": article.tts_provider or "",
            "voice_id": current_voice or "",
            "speed": article.speed or "",
            "voice_preset": article.voice_preset.id if article.voice_preset else "",
        }
        form = ArticleVoiceForm(initial=initial_data, user=request.user)

    return render(
        request,
        "text_to_audio/article_voice_settings.html",
        {"form": form, "article": article},
    )


class CostAnalyticsView(LoginRequiredMixin, TemplateView):
    """View for displaying cost analytics dashboard.

    Shows costs broken down by:
    - Total cost
    - Provider (OpenAI vs Google)
    - Model/voice
    - Feed
    - Operation type (LLM vs TTS)
    - Over time (daily)
    """

    template_name = "text_to_audio/cost_analytics.html"

    def get_context_data(self, **kwargs):
        """Build context with cost analytics data."""
        from datetime import timedelta
        from decimal import Decimal

        from django.db.models import Sum
        from django.db.models.functions import TruncDate
        from django.utils import timezone

        context = super().get_context_data(**kwargs)
        user = self.request.user

        # Get date filter from query params (default 30 days)
        days = self.request.GET.get("days", "30")
        try:
            days = int(days)
        except (ValueError, TypeError):
            days = 30

        context["selected_days"] = days

        # Check if user is admin and wants all-users view
        is_admin = hasattr(user, "profile") and user.profile.is_super_admin
        view_all = self.request.GET.get("view") == "all" and is_admin
        context["is_admin"] = is_admin
        context["view_all"] = view_all

        # Base queryset - filter by user unless admin viewing all
        if view_all:
            base_qs = OpenAIUsageStats.objects.all()
        else:
            base_qs = OpenAIUsageStats.objects.filter(user=user)

        # Apply date filter
        if days > 0:
            cutoff_date = timezone.now() - timedelta(days=days)
            base_qs = base_qs.filter(request_timestamp__gte=cutoff_date)

        # Total cost
        total_result = base_qs.aggregate(total=Sum("estimated_cost"))
        context["total_cost"] = total_result["total"] or Decimal("0")

        # Costs by operation type (LLM vs TTS)
        costs_by_operation = (
            base_qs.values("operation_type")
            .annotate(total=Sum("estimated_cost"))
            .order_by("-total")
        )
        context["costs_by_operation"] = list(costs_by_operation)

        # Costs by model
        costs_by_model = (
            base_qs.values("model_name")
            .annotate(total=Sum("estimated_cost"))
            .order_by("-total")
        )
        context["costs_by_model"] = list(costs_by_model)

        # Costs by provider - use the provider field directly
        # This is much more efficient than inferring from model name
        costs_by_provider = (
            base_qs.values("provider")
            .annotate(total=Sum("estimated_cost"))
            .order_by("-total")
        )
        # Format provider names for display (capitalize)
        context["costs_by_provider"] = [
            {"provider": (item["provider"] or "openai").capitalize(), "total": item["total"]}
            for item in costs_by_provider
            if item["total"] and item["total"] > 0
        ]

        # Costs by feed
        costs_by_feed = (
            base_qs.filter(article__isnull=False)
            .values("article__feed__name")
            .annotate(total=Sum("estimated_cost"))
            .order_by("-total")
        )
        context["costs_by_feed"] = [
            {
                "feed_name": item["article__feed__name"] or "No Feed",
                "total": item["total"],
            }
            for item in costs_by_feed
        ]

        # Costs over time (daily)
        costs_over_time = (
            base_qs.annotate(date=TruncDate("request_timestamp"))
            .values("date")
            .annotate(total=Sum("estimated_cost"))
            .order_by("date")
        )
        context["costs_over_time"] = list(costs_over_time)

        # Costs by user (admin only, when viewing all)
        if view_all:
            costs_by_user = (
                base_qs.values("user__username")
                .annotate(total=Sum("estimated_cost"))
                .order_by("-total")
            )
            context["costs_by_user"] = [
                {"username": item["user__username"], "total": item["total"]}
                for item in costs_by_user
            ]
        else:
            # For non-admins requesting view=all, show only their own data
            if self.request.GET.get("view") == "all":
                context["costs_by_user"] = [
                    {"username": user.username, "total": context["total_cost"]}
                ]

        return context
