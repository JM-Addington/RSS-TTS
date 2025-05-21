"""rss_tts URL Configuration."""

from django.contrib import admin
from django.urls import path

from text_to_audio.views import HomeView

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", HomeView.as_view(), name="home"),
]
