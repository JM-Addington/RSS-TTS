"""Django settings for rss_tts project."""

import os
from pathlib import Path

import dj_database_url

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/5.0/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "default-insecure-key-for-development")

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = os.environ.get("DJANGO_DEBUG", "False").lower() in ("1", "true", "yes")

# Optional API keys
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
# Model used when generating titles with GPT
OPENAI_TITLE_MODEL = os.environ.get("OPENAI_TITLE_MODEL", "gpt-4o-mini")
# TTS model and voice settings
OPENAI_TTS_MODEL = os.environ.get("OPENAI_TTS_MODEL", "tts-1")
OPENAI_TTS_VOICE = os.environ.get("OPENAI_TTS_VOICE", "alloy")
# Models used for content analysis and genre classification
OPENAI_ANALYSIS_MODEL = os.environ.get("OPENAI_ANALYSIS_MODEL", "gpt-4o-mini")
OPENAI_CLASSIFICATION_MODEL = os.environ.get(
    "OPENAI_CLASSIFICATION_MODEL", "gpt-4o-mini"
)

# ChunkTone LLM Service Feature Flag
ENABLE_CHUNK_TONE_LLM = os.getenv("ENABLE_CHUNK_TONE_LLM", "true").lower() == "true"

ALLOWED_HOSTS: list[str] = []
ALLOWED_HOSTS += (
    os.environ.get("DJANGO_ALLOWED_HOSTS", "").split(",")
    if os.environ.get("DJANGO_ALLOWED_HOSTS")
    else []
)

CSRF_TRUSTED_ORIGINS = (
    os.environ.get("DJANGO_CSRF_TRUSTED_ORIGINS", "").split(",")
    if os.environ.get("DJANGO_CSRF_TRUSTED_ORIGINS")
    else []
)

# Application definition

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "widget_tweaks",
    "text_to_audio",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "rss_tts.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "rss_tts.wsgi.application"

# Database
# https://docs.djangoproject.com/en/5.0/ref/settings/#databases

# Flexible database configuration
# Priority: DATABASE_URL > PostgreSQL env vars > SQLite (default)

if database_url := os.environ.get("DATABASE_URL"):
    # Use dj-database-url for DATABASE_URL parsing
    DATABASES = {
        "default": dj_database_url.config(
            default=database_url,
            conn_max_age=600,
            conn_health_checks=True,
        )
    }
elif all(
    os.environ.get(var)
    for var in ["POSTGRES_DB", "POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_HOST"]
):
    # Use explicit PostgreSQL configuration
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.environ["POSTGRES_DB"],
            "USER": os.environ["POSTGRES_USER"],
            "PASSWORD": os.environ["POSTGRES_PASSWORD"],
            "HOST": os.environ["POSTGRES_HOST"],
            "PORT": os.environ.get("POSTGRES_PORT", "5432"),
        }
    }
else:
    # Default to SQLite for local development
    data_dir = os.environ.get("SQLITE_DATA_DIR", "")
    db_path = os.path.join(data_dir, "db.sqlite3") if data_dir else "db.sqlite3"

    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": str(BASE_DIR / db_path),
        }
    }

CELERY_BROKER_URL = os.environ.get("CELERY_BROKER_URL", "redis://localhost:6379/0")
CELERY_TASK_ALWAYS_EAGER = False

# Password validation
# https://docs.djangoproject.com/en/5.0/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": (
            "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"
        ),
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

# Internationalization
# https://docs.djangoproject.com/en/5.0/topics/i18n/

LANGUAGE_CODE = "en-us"

TIME_ZONE = "UTC"

USE_I18N = True

USE_TZ = True

# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/5.0/howto/static-files/

STATIC_URL = "static/"
STATIC_ROOT = os.path.join(BASE_DIR, "staticfiles")

# Media files (User uploaded files)
MEDIA_URL = "/media/"
MEDIA_ROOT = os.path.join(BASE_DIR, "media")

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LOGIN_REDIRECT_URL = "home"
LOGIN_URL = "login"
LOGOUT_REDIRECT_URL = "home"

# RSS Feed Settings
PODCAST_IMAGE_URL = os.environ.get("PODCAST_IMAGE_URL", "")
RSS_EXTERNAL_HOSTNAME = os.environ.get("RSS_EXTERNAL_HOSTNAME", "")
SITE_URL = os.environ.get("SITE_URL", "http://localhost:8000")

# Article Processing Settings
ARTICLE_PROCESSING_TIMEOUT_SECONDS = 3600  # 1 hour
# Maximum number of words to analyze for content analysis (reduced from 750k for cost/performance)
MAX_ANALYSIS_WORDS = int(os.environ.get("MAX_ANALYSIS_WORDS", "8000"))
