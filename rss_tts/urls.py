"""rss_tts URL Configuration."""

from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import path

from text_to_audio.views import ArticleCreateView, HomeView, SignUpView

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/login/", auth_views.LoginView.as_view(), name="login"),
    path("accounts/logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("accounts/signup/", SignUpView.as_view(), name="signup"),
    path("articles/submit/", ArticleCreateView.as_view(), name="article-submit"),
    path("", HomeView.as_view(), name="home"),
]
