"""Utility functions for retrieving global configuration."""

from functools import lru_cache
from typing import Optional

from django.conf import settings

from .models import GlobalConfig


@lru_cache(maxsize=1)
def get_global_config() -> Optional[GlobalConfig]:
    """Return the single GlobalConfig instance if it exists."""
    return GlobalConfig.objects.first()


def get_openai_api_key() -> Optional[str]:
    config = get_global_config()
    return config.openai_api_key if config and config.openai_api_key else settings.OPENAI_API_KEY


def get_openai_tts_model() -> str:
    config = get_global_config()
    return config.openai_tts_model if config else settings.OPENAI_TTS_MODEL


def get_openai_tts_voice() -> str:
    config = get_global_config()
    return config.openai_tts_voice if config else settings.OPENAI_TTS_VOICE


def get_firecrawl_api_key() -> Optional[str]:
    config = get_global_config()
    return config.firecrawl_api_key if config and config.firecrawl_api_key else getattr(settings, "FIRECRAWL_API_KEY", None)


def get_use_firecrawl_by_default() -> bool:
    config = get_global_config()
    if config:
        return config.use_firecrawl_by_default
    return getattr(settings, "USE_FIRECRAWL_BY_DEFAULT", False)
