import logging

from django.conf import settings
from django.db import models

logger = logging.getLogger(__name__)


class GlobalConfig(models.Model):
    """Singleton model to store global application settings."""

    # OpenAI API Configuration
    openai_api_key = models.CharField(
        max_length=200,
        blank=True,
        null=True,
        help_text="Your OpenAI API key for text-to-speech and content analysis",
    )
    openai_title_model = models.CharField(
        max_length=100,
        default="gpt-4o-mini",
        help_text="OpenAI model used for generating article titles",
    )
    openai_tts_model = models.CharField(
        max_length=100,
        default="tts-1-hd",
        help_text="OpenAI TTS model for generating speech (tts-1 or tts-1-hd)",
    )
    openai_tts_voice = models.CharField(
        max_length=50,
        default="alloy",
        help_text="Default OpenAI TTS voice (alloy, echo, fable, onyx, nova, shimmer)",
    )
    openai_tts_response_format = models.CharField(
        max_length=20,
        default="wav",
        help_text="Audio response format from OpenAI TTS (mp3, opus, aac, flac, wav, pcm)",
    )
    openai_analysis_model = models.CharField(
        max_length=100,
        default="gpt-4.1",
        help_text="OpenAI model used for content analysis",
    )
    openai_classification_model = models.CharField(
        max_length=100,
        default="gpt-4o-mini",
        help_text="OpenAI model used for genre classification",
    )

    # Content Processing Settings
    use_gpt_for_url_extraction = models.BooleanField(
        default=True, help_text="Use GPT for extracting article text from URLs"
    )
    max_analysis_words = models.PositiveIntegerField(
        default=8000,
        help_text="Maximum number of words to analyze for content analysis",
    )

    # Firecrawl Configuration
    firecrawl_api_key = models.CharField(
        max_length=200,
        blank=True,
        null=True,
        help_text="Firecrawl API key for advanced web scraping",
    )
    use_firecrawl_by_default = models.BooleanField(
        default=False, help_text="Use Firecrawl as the default web scraping service"
    )

    # Feature Flags
    enable_chunk_tone_llm = models.BooleanField(
        default=True,
        help_text="Enable ChunkTone LLM Service for advanced voice generation",
    )

    # TTS Provider Configuration
    default_tts_provider = models.CharField(
        max_length=50,
        default="openai",
        help_text="Default TTS provider (openai, google)",
    )

    # Google Cloud TTS Configuration
    google_tts_api_key = models.CharField(
        max_length=200,
        blank=True,
        null=True,
        help_text="Google Cloud API key (simpler alternative to service account)",
    )
    google_tts_credentials_json = models.TextField(
        blank=True,
        null=True,
        help_text="Google Cloud service account credentials (JSON format)",
    )
    google_tts_default_voice_type = models.CharField(
        max_length=50,
        default="gemini",
        choices=[
            ("gemini", "Gemini TTS (multi-speaker, prompts)"),
            ("chirp3", "Chirp 3: HD (premium quality)"),
            ("neural2", "Neural2 (standard quality)"),
        ],
        help_text="Default Google TTS voice type",
    )

    # RSS/Podcast Configuration
    podcast_image_url = models.URLField(
        blank=True, null=True, help_text="URL for the default podcast cover image"
    )
    site_url = models.URLField(
        default="http://localhost:8000",
        help_text="Base URL for the site, used in RSS feeds",
    )
    rss_external_hostname = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text="External hostname for RSS feeds (if different from site_url)",
    )

    class Meta:
        verbose_name = "Global Configuration"
        verbose_name_plural = "Global Configuration"

    def __str__(self) -> str:
        return "Global Configuration"

    @classmethod
    def get_or_create_with_env_migration(cls):
        """Get or create GlobalConfig instance, migrating from environment variables if needed."""
        config, created = cls.objects.get_or_create()

        if created:
            # Auto-migrate from environment variables on first creation
            cls._migrate_from_environment(config)

        return config

    @classmethod
    def _migrate_from_environment(cls, config):
        """Migrate settings from environment variables to database config."""
        env_mappings = {
            # Field name -> (env_var_name, default_value)
            "openai_api_key": ("OPENAI_API_KEY", None),
            "openai_title_model": ("OPENAI_TITLE_MODEL", "gpt-4o-mini"),
            "openai_tts_model": ("OPENAI_TTS_MODEL", "tts-1-hd"),
            "openai_tts_voice": ("OPENAI_TTS_VOICE", "alloy"),
            "openai_tts_response_format": ("OPENAI_TTS_RESPONSE_FORMAT", "wav"),
            "openai_analysis_model": ("OPENAI_ANALYSIS_MODEL", "gpt-4.1"),
            "openai_classification_model": (
                "OPENAI_CLASSIFICATION_MODEL",
                "gpt-4o-mini",
            ),
            "use_gpt_for_url_extraction": ("USE_GPT_FOR_URL_EXTRACTION", True),
            "max_analysis_words": ("MAX_ANALYSIS_WORDS", 8000),
            "firecrawl_api_key": ("FIRECRAWL_API_KEY", None),
            "use_firecrawl_by_default": ("USE_FIRECRAWL_BY_DEFAULT", False),
            "enable_chunk_tone_llm": ("ENABLE_CHUNK_TONE_LLM", True),
            "default_tts_provider": ("DEFAULT_TTS_PROVIDER", "openai"),
            "podcast_image_url": ("PODCAST_IMAGE_URL", None),
            "site_url": ("SITE_URL", "http://localhost:8000"),
            "rss_external_hostname": ("RSS_EXTERNAL_HOSTNAME", None),
        }

        migrated_settings = []

        for field_name, (env_var, default) in env_mappings.items():
            env_value = getattr(settings, env_var, default)

            # Only migrate if environment variable has a non-default value
            if env_value is not None and env_value != default:
                # Convert string boolean values
                if isinstance(default, bool) and isinstance(env_value, str):
                    env_value = env_value.lower() in ("true", "1", "yes", "on")

                # Convert string integer values
                if isinstance(default, int) and isinstance(env_value, str):
                    try:
                        env_value = int(env_value)
                    except ValueError:
                        continue

                setattr(config, field_name, env_value)
                migrated_settings.append(f"{env_var}={env_value}")

        if migrated_settings:
            config.save()
            logger.info(
                f"Auto-migrated {len(migrated_settings)} settings from environment variables: "
                f"{', '.join(migrated_settings)}"
            )

    @classmethod
    def get_configuration_conflicts(cls):
        """Check for conflicts between environment variables and database config."""
        config = cls.objects.first()
        if not config:
            return []

        conflicts = []
        env_mappings = {
            "openai_api_key": "OPENAI_API_KEY",
            "openai_title_model": "OPENAI_TITLE_MODEL",
            "openai_tts_model": "OPENAI_TTS_MODEL",
            "openai_tts_voice": "OPENAI_TTS_VOICE",
            "openai_tts_response_format": "OPENAI_TTS_RESPONSE_FORMAT",
            "openai_analysis_model": "OPENAI_ANALYSIS_MODEL",
            "openai_classification_model": "OPENAI_CLASSIFICATION_MODEL",
            "firecrawl_api_key": "FIRECRAWL_API_KEY",
            "use_firecrawl_by_default": "USE_FIRECRAWL_BY_DEFAULT",
            "enable_chunk_tone_llm": "ENABLE_CHUNK_TONE_LLM",
            "default_tts_provider": "DEFAULT_TTS_PROVIDER",
            "podcast_image_url": "PODCAST_IMAGE_URL",
            "site_url": "SITE_URL",
            "rss_external_hostname": "RSS_EXTERNAL_HOSTNAME",
            "use_gpt_for_url_extraction": "USE_GPT_FOR_URL_EXTRACTION",
            "max_analysis_words": "MAX_ANALYSIS_WORDS",
        }

        for field_name, env_var in env_mappings.items():
            db_value = getattr(config, field_name)
            env_value = getattr(settings, env_var, None)

            # Check if both exist and are different
            if db_value and env_value and str(db_value) != str(env_value):
                conflicts.append(
                    {
                        "field": field_name,
                        "env_var": env_var,
                        "db_value": db_value,
                        "env_value": env_value,
                        "human_name": field_name.replace("_", " ").title(),
                    }
                )

        return conflicts
