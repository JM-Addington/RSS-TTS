"""URL configuration for the RSS-TTS API."""

from django.urls import path
from . import views

app_name = 'api'

urlpatterns = [
    # Authentication endpoints
    path('auth/token/create/', views.create_api_token, name='create-token'),
    path('auth/token/revoke/', views.revoke_api_token, name='revoke-token'),

    # Status endpoint
    path('status/', views.api_status, name='status'),

    # Feed endpoints
    path('feeds/', views.FeedListAPIView.as_view(), name='feed-list'),

    # Article endpoints
    path('articles/', views.ArticleListAPIView.as_view(), name='article-list'),
    path('articles/create/', views.ArticleCreateAPIView.as_view(), name='article-create'),
    path('articles/<int:id>/', views.ArticleDetailAPIView.as_view(), name='article-detail'),
]
