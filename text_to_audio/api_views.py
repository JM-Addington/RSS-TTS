"""API views for the text_to_audio app.

This module defines REST API endpoints for the RSS-TTS system.
"""

import logging
import uuid
from typing import Any, Dict

from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import serializers, status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Article, Feed
from .tasks import process_article
from .utils import fetch_url_content, process_url_to_text

logger = logging.getLogger(__name__)


class ArticleSubmissionSerializer(serializers.Serializer):
    """Serializer for article submission via API."""

    title = serializers.CharField(
        max_length=1024,
        required=False,
        allow_blank=True,
        help_text="Optional title for the article. If not provided, title will be extracted from content or generated.",
    )
    text_content = serializers.CharField(
        required=False,
        allow_blank=True,
        help_text="Text content of the article. Either text_content or source_url must be provided.",
    )
    source_url = serializers.URLField(
        max_length=2000,
        required=False,
        allow_blank=True,
        help_text="URL of the article to process. Either text_content or source_url must be provided.",
    )
    voice_id = serializers.CharField(
        max_length=50,
        required=False,
        allow_blank=True,
        help_text="Voice ID to use for TTS conversion. Leave blank to auto-detect from content.",
    )
    speed = serializers.FloatField(
        required=False,
        allow_null=True,
        help_text="Speed multiplier for TTS conversion (e.g., 1.0 for normal speed).",
    )

    def validate(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Validate that either source_url or text_content is provided."""
        source_url = data.get("source_url", "")
        text_content = data.get("text_content", "")

        # Check that at least one of source_url or text_content is provided
        if not source_url and not text_content:
            raise serializers.ValidationError(
                "You must provide either text_content or source_url."
            )

        # Check if both are provided - which is not allowed
        if source_url and text_content:
            raise serializers.ValidationError(
                "You cannot provide both text_content and source_url."
            )

        # Check text content length - max 30,000 words
        if text_content:
            word_count = len(text_content.split())
            if word_count > 30000:
                raise serializers.ValidationError(
                    f"Text content is too long ({word_count:,} words). "
                    f"Please limit to 30,000 words or less."
                )

        return data


@extend_schema_view(
    post=extend_schema(
        summary="Submit a new article",
        description="Submit a new article to a feed using either direct text content or a URL.",
        request=ArticleSubmissionSerializer,
        responses={
            201: {"description": "Article created successfully"},
            400: {"description": "Invalid input"},
            404: {"description": "Feed not found"},
        },
    )
)
class FeedArticleSubmitView(APIView):
    """API endpoint for submitting new articles to a feed."""

    def post(self, request: Request, token: uuid.UUID) -> Response:
        """Handle POST requests to submit new articles.

        Args:
            request: The HTTP request object.
            token: The feed token (UUID).

        Returns:
            An HTTP response with the submission result.
        """
        # Get the feed by token
        feed = get_object_or_404(Feed, token=token)

        # Validate request data
        serializer = ArticleSubmissionSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        # Create new article
        article = Article(
            feed=feed,
            title=serializer.validated_data.get("title", ""),
            source_url=serializer.validated_data.get("source_url", ""),
            text_content=serializer.validated_data.get("text_content", ""),
            status=Article.PROCESSING,
            audio_uuid=uuid.uuid4(),
        )

        # Set voice parameters if provided
        voice_id = serializer.validated_data.get("voice_id")
        speed = serializer.validated_data.get("speed")

        if voice_id:
            article.voice_id = voice_id

        if speed is not None:
            article.speed = speed

        # If URL is provided, validate it first
        if article.source_url:
            # AIDEV-NOTE: Uses process_url_to_text for Firecrawl fallback on 403/404/400 errors (matches /feeds/5/add/)
            # Use process_url_to_text to get both HTML and text with Firecrawl fallback support
            url_success, url_text, url_error = process_url_to_text(article.source_url)
            if not url_success:
                return Response(
                    {"error": f"Error fetching URL: {url_error}"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Set text content from URL extraction
            article.text_content = url_text

            # We need HTML for title extraction, so fetch it separately if needed
            # First try regular fetch, then fall back to Firecrawl for HTML
            success, html, error = fetch_url_content(article.source_url)
            if not success:
                # If regular fetch fails, try Firecrawl for HTML
                from django.conf import settings

                api_key = getattr(settings, "FIRECRAWL_API_KEY", None)
                if api_key and any(code in error for code in ["404", "403", "400"]):
                    from .utils import fetch_html_with_firecrawl

                    fc_success, html, fc_error = fetch_html_with_firecrawl(
                        article.source_url
                    )
                    if not fc_success:
                        # If both fail, we still have the text from process_url_to_text
                        html = f"<html><body><p>{url_text}</p></body></html>"
                else:
                    # If no API key or different error, create basic HTML from text
                    html = f"<html><body><p>{url_text}</p></body></html>"

            # Generate title if not provided
            if not article.title:
                from .utils import extract_title_from_html

                article.title = extract_title_from_html(html) or "Untitled Article"

        # Run custom validation
        try:
            article.clean()
        except Exception as e:
            return Response(
                {"error": f"Validation error: {str(e)}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Save article to database
        article.save()

        # Start processing the article
        process_article.delay(article.id)

        # Return success response without article details
        return Response({"success": True}, status=status.HTTP_201_CREATED)
