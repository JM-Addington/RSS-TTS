from django.apps import AppConfig


class AppConfigConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "appconfig"
    verbose_name = "Application Configuration"
