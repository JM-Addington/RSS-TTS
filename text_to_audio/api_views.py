from __future__ import annotations

"""API views for text_to_audio."""

import uuid

from django.http import Http404
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import VOICE_CHOICES, Article, Feed
from .tasks import process_article


class FeedArticleSubmitView(APIView):
    """Create an article for a feed using its token."""

    authentication_classes: list = []
    permission_classes: list = []

    def post(self, request, token: uuid.UUID) -> Response:
        """Handle POST requests."""
        try:
            feed = Feed.objects.get(token=token)
        except (Feed.DoesNotExist, ValueError):
            raise Http404("Feed not found")

        text = request.data.get("text") or ""
        url = request.data.get("url") or ""

        if bool(text) == bool(url):
            return Response(
                {"detail": "Provide either 'text' or 'url', not both."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        article = Article(
            feed=feed,
            text_content=text if text else "",
            source_url=url if url else "",
            audio_uuid=uuid.uuid4(),
            status=Article.PROCESSING,
        )

        if feed.default_voice_preset:
            preset = feed.default_voice_preset
            article.voice_preset = preset
            standard_voices = [v[0] for v in VOICE_CHOICES]
            if preset.voice_id in standard_voices:
                article.voice = preset.voice_id
                article.voice_id = None
            else:
                article.voice_id = preset.voice_id
                article.voice = "alloy"
            article.speed = preset.speed

        article.full_clean()
        article.save()

        task = process_article.delay(article.pk)
        article.celery_task_id = task.id
        article.save(update_fields=["celery_task_id", "updated_at"])

        return Response(
            {"id": article.pk, "audio_uuid": str(article.audio_uuid)},
            status=status.HTTP_201_CREATED,
        )
