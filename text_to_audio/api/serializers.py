"""API Serializers for the RSS-TTS system."""

from rest_framework import serializers
from django.contrib.auth import get_user_model

from ..models import Feed, Article

User = get_user_model()


class FeedSerializer(serializers.ModelSerializer):
    """Serializer for Feed model."""

    class Meta:
        model = Feed
        fields = [
            'id',
            'name',
            'token',
            'voice_mode',
            'created_at'
        ]
        read_only_fields = ['id', 'token', 'created_at']


class ArticleCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating articles via API."""

    feed_token = serializers.UUIDField(write_only=True, help_text="Feed token to identify which feed to add article to")

    class Meta:
        model = Article
        fields = [
            'feed_token',
            'title',
            'source_url',
            'text_content'
        ]

    def validate(self, attrs):
        """Validate that either source_url or text_content is provided."""
        source_url = attrs.get('source_url')
        text_content = attrs.get('text_content')
        title = attrs.get('title')

        if not source_url and not text_content:
            raise serializers.ValidationError(
                "Either 'source_url' or 'text_content' must be provided."
            )

        if source_url and text_content:
            raise serializers.ValidationError(
                "Provide either 'source_url' or 'text_content', not both."
            )

        if text_content and not title:
            raise serializers.ValidationError(
                "When providing 'text_content', 'title' is required."
            )

        return attrs

    def create(self, validated_data):
        """Create article and associate with feed."""
        feed_token = validated_data.pop('feed_token')
        user = self.context['request'].user

        try:
            feed = Feed.objects.get(token=feed_token, user=user)
        except Feed.DoesNotExist:
            raise serializers.ValidationError({
                'feed_token': 'Invalid feed token or you do not have access to this feed.'
            })

        article = Article.objects.create(feed=feed, **validated_data)

        # Import and dispatch Celery task for processing
        from ..tasks import process_article
        task = process_article.delay(article.id)
        article.celery_task_id = task.id
        article.save(update_fields=['celery_task_id'])

        return article


class ArticleDetailSerializer(serializers.ModelSerializer):
    """Serializer for article details including processing status."""

    feed_name = serializers.CharField(source='feed.name', read_only=True)
    audio_url = serializers.SerializerMethodField()

    class Meta:
        model = Article
        fields = [
            'id',
            'feed_name',
            'title',
            'source_url',
            'status',
            'error_message',
            'audio_url',
            'detected_genre',
            'created_at',
            'updated_at'
        ]
        read_only_fields = ['id', 'feed_name', 'status', 'error_message', 'audio_url', 'detected_genre', 'created_at', 'updated_at']

    def get_audio_url(self, obj):
        """Get the audio URL if processing is completed."""
        if obj.status == Article.COMPLETED and obj.audio_uuid:
            request = self.context.get('request')
            if request:
                from django.conf import settings
                # Use SITE_URL setting or build from request
                base_url = getattr(settings, 'SITE_URL', '')
                if not base_url and request:
                    base_url = f"{request.scheme}://{request.get_host()}"
                return f"{base_url}/audio/{obj.audio_uuid}/"
        return None


class UserTokenSerializer(serializers.Serializer):
    """Serializer for creating/retrieving user API tokens."""

    token = serializers.CharField(read_only=True)
    created = serializers.BooleanField(read_only=True)
