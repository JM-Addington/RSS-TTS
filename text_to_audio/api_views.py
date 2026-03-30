"""API views for the text_to_audio app.

This module defines REST API endpoints for the RSS-TTS system.
"""

import logging
import math
import uuid
from typing import Any, Dict

from django.core.exceptions import ValidationError as DjangoValidationError
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import generics, serializers, status
from rest_framework.exceptions import NotFound
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from kombu.exceptions import OperationalError as KombuOperationalError
from redis.exceptions import ConnectionError as RedisConnectionError

from .models import VOICE_CHOICES, Article, Feed, UserVoicePreset
from .tasks import process_article
from .validators import validate_url_not_ssrf

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
        max_length=500000,
        required=False,
        allow_blank=True,
        help_text="Text content of the article. Either text_content or source_url must be provided.",
    )
    # AIDEV-NOTE: SSRF validator blocks private IPs, cloud metadata, non-HTTP schemes (#190)
    source_url = serializers.URLField(
        max_length=2000,
        required=False,
        allow_blank=True,
        validators=[validate_url_not_ssrf],
        help_text="URL of the article to process. Either text_content or source_url must be provided.",
    )
    voice_id = serializers.CharField(
        max_length=50,
        required=False,
        allow_blank=True,
        help_text="Voice ID to use for TTS conversion. Leave blank to auto-detect from content.",
    )
    # AIDEV-NOTE: Speed bounds 0.25-4.0 match OpenAI TTS API limits
    speed = serializers.FloatField(
        required=False,
        allow_null=True,
        min_value=0.25,
        max_value=4.0,
        help_text="Speed multiplier for TTS conversion (0.25 to 4.0, default 1.0).",
    )

    # AIDEV-NOTE: NaN bypasses DRF min/max validators since NaN comparisons are always False
    def validate_speed(self, value):
        """Reject NaN and Infinity speed values."""
        if value is not None and not math.isfinite(value):
            raise serializers.ValidationError(
                "Speed must be a finite number between 0.25 and 4.0."
            )
        return value

    # AIDEV-NOTE: voice_id validated against VOICE_CHOICES for consistency with form/model (#198)
    def validate_voice_id(self, value):
        """Validate voice_id against known VOICE_CHOICES."""
        if not value:  # allow blank/empty (field is optional)
            return value
        valid_ids = {choice[0] for choice in VOICE_CHOICES}
        if value not in valid_ids:
            raise serializers.ValidationError(
                f"Invalid voice_id '{value}'. Use a valid voice ID from the available voices list."
            )
        return value

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

        # Check text content length - max 40,000 words
        if text_content:
            word_count = len(text_content.split())
            if word_count > 40000:
                raise serializers.ValidationError(
                    f"Text content is too long ({word_count:,} words). "
                    f"Please limit to 40,000 words or less."
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
        # AIDEV-NOTE: Explicit lookup raises DRF NotFound for JSON 404 instead of Django HTML 404 (#195)
        try:
            feed = Feed.objects.get(token=token)
        except Feed.DoesNotExist:
            raise NotFound("Feed not found.")

        # Validate request data — raise_exception lets DRF route errors through exception handler
        serializer = ArticleSubmissionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

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

        # AIDEV-NOTE: URL fetching is done ASYNC in process_article task to avoid blocking API
        # For URL submissions, we just save the URL and let the Celery task handle fetching
        # Title will be extracted from URL in the task if not provided
        if article.source_url and not article.title:
            article.title = "Processing..."  # Placeholder, will be updated by task

        # AIDEV-NOTE: Catch only DjangoValidationError; log others; never leak internals (#193)
        try:
            article.clean()
        except DjangoValidationError:
            return Response(
                {"error": "Article validation failed"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception:
            logger.exception("Unexpected error during article validation")
            return Response(
                {"error": "An internal error occurred"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        # Save article to database
        article.save()

        # AIDEV-NOTE: Catch broker/redis errors — article saved, return 503 if queuing fails
        try:
            process_article.delay(article.id)
        except (KombuOperationalError, RedisConnectionError) as exc:
            logger.error("Failed to queue article processing: %s", exc)
            return Response(
                {
                    "success": False,
                    "error": "Task queue unavailable. Article saved but processing could not be started.",
                },
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        return Response(
            {
                "success": True,
                "id": article.id,
                "audio_uuid": str(article.audio_uuid),
                "status": article.status,
            },
            status=status.HTTP_201_CREATED,
        )


class VoicePresetSerializer(serializers.ModelSerializer):
    """Serializer for UserVoicePreset model."""

    # AIDEV-NOTE: Override model field to add speed bounds validation (#196)
    speed = serializers.FloatField(
        default=1.0,
        min_value=0.25,
        max_value=4.0,
    )

    class Meta:
        model = UserVoicePreset
        fields = [
            "id",
            "name",
            "voice_id",
            "speed",
            "affect",
            "tone",
            "pacing",
            "pitch_variation",
            "speaking_style",
            "prompt",
            "sample_input",
            "description",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


@extend_schema_view(
    get=extend_schema(
        summary="List voice presets",
        description="Returns all voice presets for the authenticated user, paginated.",
        responses={
            200: VoicePresetSerializer(many=True),
            401: {"description": "Authentication required"},
        },
    ),
    post=extend_schema(
        summary="Create voice preset",
        description="Creates a new voice preset for the authenticated user.",
        request=VoicePresetSerializer,
        responses={
            201: VoicePresetSerializer,
            400: {"description": "Invalid input or duplicate name"},
            401: {"description": "Authentication required"},
        },
    ),
)
# AIDEV-NOTE: ListCreateAPIView provides automatic pagination via global PAGE_SIZE=20 (#191)
class VoicePresetListView(generics.ListCreateAPIView):
    """API endpoint for listing and creating voice presets."""

    serializer_class = VoicePresetSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return UserVoicePreset.objects.filter(user=self.request.user).order_by("name")

    def perform_create(self, serializer):
        # Check for duplicate name — raise as field-level ValidationError for consistent format
        name = serializer.validated_data.get("name")
        if UserVoicePreset.objects.filter(user=self.request.user, name=name).exists():
            raise serializers.ValidationError(
                {"name": ["A preset with this name already exists."]}
            )
        serializer.save(user=self.request.user)


@extend_schema_view(
    get=extend_schema(
        summary="Get voice preset detail",
        description="Returns a single voice preset by ID.",
        responses={
            200: VoicePresetSerializer,
            401: {"description": "Authentication required"},
            404: {"description": "Preset not found"},
        },
    )
)
class VoicePresetDetailView(APIView):
    """API endpoint for retrieving a single voice preset."""

    permission_classes = [IsAuthenticated]

    def get(self, request: Request, preset_id: int) -> Response:
        """Return a single voice preset by ID.

        Args:
            request: The HTTP request object.
            preset_id: The ID of the preset to retrieve.

        Returns:
            The voice preset details.
        """
        # Only return presets belonging to the authenticated user
        try:
            preset = UserVoicePreset.objects.get(id=preset_id, user=request.user)
        except UserVoicePreset.DoesNotExist:
            raise NotFound("Voice preset not found.")
        serializer = VoicePresetSerializer(preset)
        return Response(serializer.data)
