from django.test import TestCase, override_settings

from appconfig.models import GlobalConfig
from appconfig.utils import (
    get_default_tts_provider,
    get_enable_chunk_tone_llm,
    get_firecrawl_api_key,
    get_global_config,
    get_max_analysis_words,
    get_openai_analysis_model,
    get_openai_api_key,
    get_openai_classification_model,
    get_openai_title_model,
    get_openai_tts_model,
    get_openai_tts_voice,
    get_podcast_image_url,
    get_site_url,
    get_use_firecrawl_by_default,
    get_use_gpt_for_url_extraction,
)


class GlobalConfigTests(TestCase):
    """Tests for global configuration overrides."""

    def setUp(self):
        """Clear any existing global config and cache before each test."""
        GlobalConfig.objects.all().delete()
        # Clear the LRU cache
        get_global_config.cache_clear()

    @override_settings(
        OPENAI_API_KEY="env-key",
        OPENAI_TTS_MODEL="model-env",
        OPENAI_TTS_VOICE="env-voice",
        OPENAI_TITLE_MODEL="title-env",
        FIRECRAWL_API_KEY="firecrawl-env",
        USE_FIRECRAWL_BY_DEFAULT=True,
        ENABLE_CHUNK_TONE_LLM=False,
        DEFAULT_TTS_PROVIDER="google",
        PODCAST_IMAGE_URL="http://example.com/image.jpg",
        SITE_URL="http://env-site.com",
        USE_GPT_FOR_URL_EXTRACTION=False,
        MAX_ANALYSIS_WORDS=5000,
    )
    def test_defaults_fallback_to_settings(self):
        self.assertEqual(get_openai_api_key(), "env-key")
        self.assertEqual(get_openai_tts_model(), "model-env")
        self.assertEqual(get_openai_tts_voice(), "env-voice")
        self.assertEqual(get_openai_title_model(), "title-env")
        self.assertEqual(get_firecrawl_api_key(), "firecrawl-env")
        self.assertEqual(get_use_firecrawl_by_default(), True)
        self.assertEqual(get_enable_chunk_tone_llm(), False)
        self.assertEqual(get_default_tts_provider(), "google")
        self.assertEqual(get_podcast_image_url(), "http://example.com/image.jpg")
        self.assertEqual(get_site_url(), "http://env-site.com")
        self.assertEqual(get_use_gpt_for_url_extraction(), False)
        self.assertEqual(get_max_analysis_words(), 5000)

    @override_settings(
        OPENAI_API_KEY="env-key",
        OPENAI_TTS_MODEL="model-env",
        OPENAI_TTS_VOICE="env-voice",
        OPENAI_TITLE_MODEL="title-env",
        FIRECRAWL_API_KEY="firecrawl-env",
        USE_FIRECRAWL_BY_DEFAULT=False,
        ENABLE_CHUNK_TONE_LLM=True,
        DEFAULT_TTS_PROVIDER="openai",
        PODCAST_IMAGE_URL="http://example.com/image.jpg",
        SITE_URL="http://env-site.com",
        USE_GPT_FOR_URL_EXTRACTION=True,
        MAX_ANALYSIS_WORDS=8000,
    )
    def test_db_overrides_settings(self):
        GlobalConfig.objects.create(
            openai_api_key="db-key",
            openai_tts_model="db-model",
            openai_tts_voice="db-voice",
            openai_title_model="db-title",
            firecrawl_api_key="db-firecrawl",
            use_firecrawl_by_default=True,
            enable_chunk_tone_llm=False,
            default_tts_provider="google",
            podcast_image_url="http://db.com/image.jpg",
            site_url="http://db-site.com",
            use_gpt_for_url_extraction=False,
            max_analysis_words=6000,
        )
        # Clear cache after creating the config
        get_global_config.cache_clear()

        self.assertEqual(get_openai_api_key(), "db-key")
        self.assertEqual(get_openai_tts_model(), "db-model")
        self.assertEqual(get_openai_tts_voice(), "db-voice")
        self.assertEqual(get_openai_title_model(), "db-title")
        self.assertEqual(get_firecrawl_api_key(), "db-firecrawl")
        self.assertEqual(get_use_firecrawl_by_default(), True)
        self.assertEqual(get_enable_chunk_tone_llm(), False)
        self.assertEqual(get_default_tts_provider(), "google")
        self.assertEqual(get_podcast_image_url(), "http://db.com/image.jpg")
        self.assertEqual(get_site_url(), "http://db-site.com")
        self.assertEqual(get_use_gpt_for_url_extraction(), False)
        self.assertEqual(get_max_analysis_words(), 6000)

    @override_settings(
        OPENAI_API_KEY=None, FIRECRAWL_API_KEY=None, PODCAST_IMAGE_URL=None
    )
    def test_default_values_with_no_config(self):
        """Test that defaults are used when no config exists and no settings."""
        # Test functions that have hardcoded defaults
        self.assertEqual(get_openai_title_model(), "gpt-4o-mini")
        self.assertEqual(get_openai_analysis_model(), "gpt-4.1")
        self.assertEqual(get_openai_classification_model(), "gpt-4o-mini")
        self.assertEqual(get_openai_tts_model(), "tts-1-hd")
        self.assertEqual(get_openai_tts_voice(), "alloy")
        self.assertEqual(get_use_gpt_for_url_extraction(), True)
        self.assertEqual(get_max_analysis_words(), 8000)
        self.assertEqual(get_use_firecrawl_by_default(), False)
        self.assertEqual(get_enable_chunk_tone_llm(), True)
        self.assertEqual(get_default_tts_provider(), "openai")
        self.assertEqual(get_site_url(), "http://localhost:8000")

        # Test functions that return None when no config
        self.assertIsNone(get_openai_api_key())
        self.assertIsNone(get_firecrawl_api_key())
        self.assertIsNone(get_podcast_image_url())

    def test_partial_config_overrides(self):
        """Test that only specified fields override defaults."""
        GlobalConfig.objects.create(
            openai_api_key="partial-key",
            use_firecrawl_by_default=True,
            # Leave other fields as defaults
        )
        # Clear cache after creating the config
        get_global_config.cache_clear()

        # Should use DB values
        self.assertEqual(get_openai_api_key(), "partial-key")
        self.assertEqual(get_use_firecrawl_by_default(), True)

        # Should use model defaults
        self.assertEqual(get_openai_tts_model(), "tts-1-hd")
        self.assertEqual(get_openai_tts_voice(), "alloy")
        self.assertEqual(get_default_tts_provider(), "openai")

    @override_settings(
        OPENAI_API_KEY="env-key-123",
        FIRECRAWL_API_KEY="firecrawl-key-456",
        USE_FIRECRAWL_BY_DEFAULT=True,
        SITE_URL="http://test-env.com",
    )
    def test_auto_migration_from_environment(self):
        """Test that environment variables are auto-migrated on first config access."""
        # Clear any existing config and cache
        GlobalConfig.objects.all().delete()
        get_global_config.cache_clear()

        # First access should trigger auto-migration
        config = get_global_config()

        self.assertIsNotNone(config)
        self.assertEqual(config.openai_api_key, "env-key-123")
        self.assertEqual(config.firecrawl_api_key, "firecrawl-key-456")
        self.assertEqual(config.use_firecrawl_by_default, True)
        self.assertEqual(config.site_url, "http://test-env.com")

    def test_conflict_detection(self):
        """Test that configuration conflicts are properly detected."""
        # Create a config with some values
        GlobalConfig.objects.create(
            openai_api_key="db-key",
            site_url="http://db-site.com",
        )

        # Mock environment settings with conflicting values
        with self.settings(OPENAI_API_KEY="env-key", SITE_URL="http://env-site.com"):
            conflicts = GlobalConfig.get_configuration_conflicts()

            self.assertEqual(len(conflicts), 2)

            # Check that conflicts are properly identified
            conflict_fields = [c["field"] for c in conflicts]
            self.assertIn("openai_api_key", conflict_fields)
            self.assertIn("site_url", conflict_fields)

            # Check conflict details
            openai_conflict = next(
                c for c in conflicts if c["field"] == "openai_api_key"
            )
            self.assertEqual(openai_conflict["db_value"], "db-key")
            self.assertEqual(openai_conflict["env_value"], "env-key")
            self.assertEqual(openai_conflict["env_var"], "OPENAI_API_KEY")

    def test_no_conflicts_when_values_match(self):
        """Test that no conflicts are detected when DB and env values match."""
        GlobalConfig.objects.create(
            openai_api_key="same-key",
            site_url="http://same-site.com",
        )

        with self.settings(OPENAI_API_KEY="same-key", SITE_URL="http://same-site.com"):
            conflicts = GlobalConfig.get_configuration_conflicts()
            self.assertEqual(len(conflicts), 0)

    @override_settings(OPENAI_TTS_MODEL="custom-model")
    def test_migration_skips_defaults(self):
        """Test that migration only occurs for non-default environment values."""
        GlobalConfig.objects.all().delete()
        get_global_config.cache_clear()

        # This should not migrate the TTS model since it's not set in env
        # But should migrate the custom model that is set
        config = get_global_config()

        # Should use custom env value
        self.assertEqual(config.openai_tts_model, "custom-model")

        # Should use model default (not environment default)
        self.assertEqual(config.openai_tts_voice, "alloy")
