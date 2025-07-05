from django.test import TestCase, override_settings

from appconfig.models import GlobalConfig
from appconfig.utils import (
    get_openai_api_key,
    get_openai_tts_model,
    get_openai_tts_voice,
)


class GlobalConfigTests(TestCase):
    """Tests for global configuration overrides."""

    @override_settings(OPENAI_API_KEY="env-key", OPENAI_TTS_MODEL="model-env", OPENAI_TTS_VOICE="env-voice")
    def test_defaults_fallback_to_settings(self):
        self.assertEqual(get_openai_api_key(), "env-key")
        self.assertEqual(get_openai_tts_model(), "model-env")
        self.assertEqual(get_openai_tts_voice(), "env-voice")

    @override_settings(OPENAI_API_KEY="env-key", OPENAI_TTS_MODEL="model-env", OPENAI_TTS_VOICE="env-voice")
    def test_db_overrides_settings(self):
        GlobalConfig.objects.create(
            openai_api_key="db-key",
            openai_tts_model="db-model",
            openai_tts_voice="db-voice",
        )
        self.assertEqual(get_openai_api_key(), "db-key")
        self.assertEqual(get_openai_tts_model(), "db-model")
        self.assertEqual(get_openai_tts_voice(), "db-voice")
