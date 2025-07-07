"""Utility functions for retrieving global configuration."""

from functools import lru_cache
from typing import Optional

from django.conf import settings

from .models import GlobalConfig


@lru_cache(maxsize=1)
def get_global_config() -> Optional[GlobalConfig]:
    """Return the single GlobalConfig instance, creating and migrating if needed."""
    return GlobalConfig.get_or_create_with_env_migration()


# OpenAI API Configuration
def get_openai_api_key() -> Optional[str]:
    config = get_global_config()
    return (
        config.openai_api_key
        if config and config.openai_api_key
        else settings.OPENAI_API_KEY
    )


def get_openai_title_model() -> str:
    config = get_global_config()
    return (
        config.openai_title_model
        if config
        else getattr(settings, "OPENAI_TITLE_MODEL", "gpt-4o-mini")
    )


def get_openai_tts_model() -> str:
    config = get_global_config()
    return (
        config.openai_tts_model
        if config
        else getattr(settings, "OPENAI_TTS_MODEL", "tts-1-hd")
    )


def get_openai_tts_voice() -> str:
    config = get_global_config()
    return (
        config.openai_tts_voice
        if config
        else getattr(settings, "OPENAI_TTS_VOICE", "alloy")
    )


def get_openai_tts_response_format() -> str:
    config = get_global_config()
    return (
        config.openai_tts_response_format
        if config
        else getattr(settings, "OPENAI_TTS_RESPONSE_FORMAT", "wav")
    )


def get_openai_analysis_model() -> str:
    config = get_global_config()
    return (
        config.openai_analysis_model
        if config
        else getattr(settings, "OPENAI_ANALYSIS_MODEL", "gpt-4.1")
    )


def get_openai_classification_model() -> str:
    config = get_global_config()
    return (
        config.openai_classification_model
        if config
        else getattr(settings, "OPENAI_CLASSIFICATION_MODEL", "gpt-4o-mini")
    )


# Content Processing Settings
def get_use_gpt_for_url_extraction() -> bool:
    config = get_global_config()
    if config is not None:
        return config.use_gpt_for_url_extraction
    return getattr(settings, "USE_GPT_FOR_URL_EXTRACTION", True)


def get_max_analysis_words() -> int:
    config = get_global_config()
    return (
        config.max_analysis_words
        if config
        else getattr(settings, "MAX_ANALYSIS_WORDS", 8000)
    )


# Firecrawl Configuration
def get_firecrawl_api_key() -> Optional[str]:
    config = get_global_config()
    return (
        config.firecrawl_api_key
        if config and config.firecrawl_api_key
        else getattr(settings, "FIRECRAWL_API_KEY", None)
    )


def get_use_firecrawl_by_default() -> bool:
    config = get_global_config()
    if config is not None:
        return config.use_firecrawl_by_default
    return getattr(settings, "USE_FIRECRAWL_BY_DEFAULT", False)


# Feature Flags
def get_enable_chunk_tone_llm() -> bool:
    config = get_global_config()
    if config is not None:
        return config.enable_chunk_tone_llm
    return getattr(settings, "ENABLE_CHUNK_TONE_LLM", True)


# TTS Provider Configuration
def get_default_tts_provider() -> str:
    config = get_global_config()
    return (
        config.default_tts_provider
        if config
        else getattr(settings, "DEFAULT_TTS_PROVIDER", "openai")
    )


# RSS/Podcast Configuration
def get_podcast_image_url() -> Optional[str]:
    config = get_global_config()
    return (
        config.podcast_image_url
        if config and config.podcast_image_url
        else getattr(settings, "PODCAST_IMAGE_URL", None)
    )


def get_site_url() -> str:
    config = get_global_config()
    return (
        config.site_url
        if config and config.site_url
        else getattr(settings, "SITE_URL", None) or "http://localhost:8000"
    )


def get_rss_external_hostname() -> Optional[str]:
    config = get_global_config()
    return (
        config.rss_external_hostname
        if config and config.rss_external_hostname
        else getattr(settings, "RSS_EXTERNAL_HOSTNAME", None)
    )
