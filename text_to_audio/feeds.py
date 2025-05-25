"""Syndication feeds for the text_to_audio app.

This module implements the RSS feed generation for the RSS-to-TTS system,
providing podcast-compatible feeds with MP3 enclosures.
"""

import os
from typing import Any, Dict, Iterable

from django.conf import settings
from django.contrib.syndication.views import Feed
from django.http import Http404
from django.urls import reverse
from django.utils.feedgenerator import Rss201rev2Feed

from .models import Article
from .models import Feed as FeedModel


class ExtendedRSSFeed(Rss201rev2Feed):
    """Extended RSS feed generator with podcast-specific elements."""

    def root_attributes(self) -> Dict[str, str]:
        """Return feed root element attributes including podcast namespace."""
        attrs = super().root_attributes()
        attrs["xmlns:itunes"] = "http://www.itunes.com/dtds/podcast-1.0.dtd"
        attrs["xmlns:content"] = "http://purl.org/rss/1.0/modules/content/"
        return attrs

    def add_root_elements(self, handler: Any) -> None:
        """Add podcast-specific root elements to the feed."""
        super().add_root_elements(handler)

        # iTunes elements required for podcast apps
        handler.addQuickElement("itunes:explicit", "false")
        handler.addQuickElement("itunes:type", "episodic")
        handler.addQuickElement(
            "itunes:image",
            "",
            {
                "href": (
                    settings.PODCAST_IMAGE_URL
                    if hasattr(settings, "PODCAST_IMAGE_URL")
                    else ""
                )
            },
        )

        # Author info
        handler.startElement("itunes:author", {})
        handler.characters("RSS-TTS")
        handler.endElement("itunes:author")

        # Category - using generic "Technology" as default
        handler.startElement("itunes:category", {"text": "Technology"})
        handler.endElement("itunes:category")

        # Feed summary/description
        handler.startElement("itunes:summary", {})
        handler.characters("Audio versions of web articles")
        handler.endElement("itunes:summary")


class UserFeed(Feed):
    """Generates an RSS feed for a user's articles."""

    feed_type = ExtendedRSSFeed

    def get_object(self, request, token: str) -> FeedModel:
        """Get the feed object based on the token in the URL.

        Args:
            request: The HTTP request.
            token: The feed token from the URL.

        Returns:
            The feed object.

        Raises:
            Http404: If no feed is found with the given token.
        """
        try:
            return FeedModel.objects.get(token=token)
        except (FeedModel.DoesNotExist, ValueError):
            raise Http404("Feed not found")

    def title(self, obj: FeedModel) -> str:
        """Get the feed title."""
        return f"{obj.name} - RSS-TTS"

    def link(self, obj: FeedModel) -> str:
        """Get the feed link."""
        feed_url = reverse("feed", kwargs={"token": obj.token})

        # Use SITE_URL from settings if available
        if hasattr(settings, "SITE_URL"):
            return f"{settings.SITE_URL.rstrip('/')}{feed_url}"

        # Otherwise, the framework will use the current request's domain
        return feed_url

    def description(self, obj: FeedModel) -> str:
        """Get the feed description."""
        return f"Audio versions of articles from {obj.name}"

    def items(self, obj: FeedModel) -> Iterable[Article]:
        """Return articles associated with this feed that have completed processing."""
        return (
            Article.objects.filter(
                feed=obj,
                status=Article.COMPLETED,
                audio_file_path__isnull=False,
            )
            .exclude(audio_file_path="")
            .order_by("-created_at")
        )

    def item_title(self, item: Article) -> str:
        """Get the title for a feed item."""
        return str(item.title)

    def item_description(self, item: Article) -> str:
        """Get the description for a feed item."""
        if item.summary:
            return str(item.summary)
        if item.source_url:
            return f"Audio version of <a href='{item.source_url}'>{item.title}</a>"
        return "Audio version of article"

    def get_feed(self, obj, request):
        """Store the request for use in item_enclosure_url."""
        self.request = request
        return super().get_feed(obj, request)

    def item_enclosure_url(self, item: Article) -> str:
        """Get the enclosure URL for a feed item (MP3 file)."""
        # Ensure article has audio_uuid
        if not item.audio_uuid:
            raise ValueError(f"Article {item.pk} has no audio_uuid set")

        media_url = reverse("article-media", kwargs={"audio_uuid": item.audio_uuid})

        # Use RSS_EXTERNAL_HOSTNAME if available
        if (
            hasattr(settings, "RSS_EXTERNAL_HOSTNAME")
            and settings.RSS_EXTERNAL_HOSTNAME
        ):
            domain = settings.RSS_EXTERNAL_HOSTNAME
            protocol = "https"  # Assume HTTPS for external hostnames
            return f"{protocol}://{domain}{media_url}"

        # Otherwise use SITE_URL if available
        elif hasattr(settings, "SITE_URL"):
            return f"{settings.SITE_URL.rstrip('/')}{media_url}"

        # Fallback to request.get_host() if available
        if hasattr(self, "request"):
            domain = self.request.get_host()
            protocol = "https" if self.request.is_secure() else "http"
            return f"{protocol}://{domain}{media_url}"

        # Last resort fallback
        return media_url

    def item_enclosure_length(self, item: Article) -> int:
        """Get the size of the MP3 file."""
        # Try to get actual file size
        try:
            file_path = item.audio_file_path
            if not os.path.isabs(file_path):
                file_path = os.path.join(settings.MEDIA_ROOT, file_path)

            if os.path.exists(file_path):
                return os.path.getsize(file_path)
        except (OSError, ValueError):
            pass

        # Fall back to a default size if file can't be found
        return 1000000  # 1MB default

    def item_enclosure_mime_type(self, item: Article) -> str:
        """Get the MIME type for the enclosure."""
        return "audio/mpeg"

    def item_pubdate(self, item: Article):
        """Get the publication date for a feed item."""
        return item.created_at

    def item_link(self, item: Article) -> str:
        """Get the link for a feed item.

        This method is required by Django's syndication framework when
        the model doesn't have a get_absolute_url() method.

        Returns:
            The URL to the original article or the article media URL.
        """
        if item.source_url:
            return str(item.source_url)

        # If no source URL, return the media URL
        # Ensure article has audio_uuid
        if not item.audio_uuid:
            raise ValueError(f"Article {item.pk} has no audio_uuid set")

        media_url = reverse("article-media", kwargs={"audio_uuid": item.audio_uuid})

        # Use RSS_EXTERNAL_HOSTNAME if available
        if (
            hasattr(settings, "RSS_EXTERNAL_HOSTNAME")
            and settings.RSS_EXTERNAL_HOSTNAME
        ):
            domain = settings.RSS_EXTERNAL_HOSTNAME
            protocol = "https"  # Assume HTTPS for external hostnames
            return f"{protocol}://{domain}{media_url}"

        # Otherwise use SITE_URL if available
        elif hasattr(settings, "SITE_URL"):
            return f"{settings.SITE_URL.rstrip('/')}{media_url}"

        # Fallback to request.get_host() if available
        if hasattr(self, "request"):
            domain = self.request.get_host()
            protocol = "https" if self.request.is_secure() else "http"
            return f"{protocol}://{domain}{media_url}"

        # Last resort fallback
        return media_url
