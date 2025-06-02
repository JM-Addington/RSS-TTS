"""API Views for the RSS-TTS system."""

from rest_framework import generics, status, permissions
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.authtoken.models import Token
from django.contrib.auth import get_user_model
from django.shortcuts import get_object_or_404

from ..models import Feed, Article
from .serializers import (
    FeedSerializer,
    ArticleCreateSerializer,
    ArticleDetailSerializer,
    UserTokenSerializer
)

User = get_user_model()


class FeedListAPIView(generics.ListAPIView):
    """List all feeds for the authenticated user."""

    serializer_class = FeedSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        """Return feeds for the current user only."""
        return Feed.objects.filter(user=self.request.user)


class ArticleCreateAPIView(generics.CreateAPIView):
    """Create a new article for processing."""

    serializer_class = ArticleCreateSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_serializer_context(self):
        """Add request to serializer context for feed validation."""
        context = super().get_serializer_context()
        context['request'] = self.request
        return context


class ArticleDetailAPIView(generics.RetrieveAPIView):
    """Retrieve details of a specific article."""

    serializer_class = ArticleDetailSerializer
    permission_classes = [permissions.IsAuthenticated]
    lookup_field = 'id'

    def get_queryset(self):
        """Return articles for the current user only."""
        return Article.objects.filter(feed__user=self.request.user)


class ArticleListAPIView(generics.ListAPIView):
    """List all articles for the authenticated user."""

    serializer_class = ArticleDetailSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        """Return articles for the current user only."""
        queryset = Article.objects.filter(feed__user=self.request.user)

        # Optional filtering by feed
        feed_id = self.request.query_params.get('feed_id')
        if feed_id:
            queryset = queryset.filter(feed_id=feed_id)

        # Optional filtering by status
        status_filter = self.request.query_params.get('status')
        if status_filter:
            queryset = queryset.filter(status=status_filter)

        return queryset.order_by('-created_at')


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def create_api_token(request):
    """Create or retrieve an API token for the authenticated user."""
    user = request.user
    token, created = Token.objects.get_or_create(user=user)

    serializer = UserTokenSerializer({
        'token': token.key,
        'created': created
    })

    return Response(serializer.data, status=status.HTTP_200_OK)


@api_view(['DELETE'])
@permission_classes([permissions.IsAuthenticated])
def revoke_api_token(request):
    """Revoke the API token for the authenticated user."""
    user = request.user

    try:
        token = Token.objects.get(user=user)
        token.delete()
        return Response({'message': 'Token revoked successfully'}, status=status.HTTP_200_OK)
    except Token.DoesNotExist:
        return Response({'error': 'No token found for user'}, status=status.HTTP_404_NOT_FOUND)


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def api_status(request):
    """Get API status and user information."""
    user = request.user

    # Check if user has a token
    has_token = Token.objects.filter(user=user).exists()

    # Get user's feed and article counts
    feed_count = Feed.objects.filter(user=user).count()
    article_count = Article.objects.filter(feed__user=user).count()

    return Response({
        'user': user.username,
        'has_api_token': has_token,
        'feed_count': feed_count,
        'article_count': article_count,
        'api_version': 'v1'
    })
