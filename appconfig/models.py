from django.db import models


class GlobalConfig(models.Model):
    """Singleton model to store global application settings."""

    openai_api_key = models.CharField(max_length=200, blank=True, null=True)
    openai_tts_model = models.CharField(max_length=100, default="tts-1-hd")
    openai_tts_voice = models.CharField(max_length=50, default="alloy")
    firecrawl_api_key = models.CharField(max_length=200, blank=True, null=True)
    use_firecrawl_by_default = models.BooleanField(default=False)

    class Meta:
        verbose_name = "Global Configuration"
        verbose_name_plural = "Global Configuration"

    def __str__(self) -> str:
        return "Global Configuration"
