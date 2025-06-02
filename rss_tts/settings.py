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
OPENAI_TTS_MODEL = os.environ.get("OPENAI_TTS_MODEL", "gpt-4o-mini-tts")
OPENAI_TTS_VOICE = os.environ.get("OPENAI_TTS_VOICE", "alloy")
# Model used for ChunkToneService (intelligent text chunking and voice analysis)
OPENAI_CHUNK_TONE_MODEL = os.environ.get("OPENAI_CHUNK_TONE_MODEL", "gpt-4.1")
# Model used for ContentAnalysisService (multi-voice content analysis and AUTO voice mode)
OPENAI_CONTENT_ANALYSIS_MODEL = os.environ.get(
    "OPENAI_CONTENT_ANALYSIS_MODEL", "gpt-4.1"
)
# Model used for genre classification
OPENAI_CLASSIFICATION_MODEL = os.environ.get(
    "OPENAI_CLASSIFICATION_MODEL", "gpt-4o-mini"
)

# ChunkTone LLM Service Feature Flag
ENABLE_CHUNK_TONE_LLM = os.getenv("ENABLE_CHUNK_TONE_LLM", "true").lower() == "true"

# Parallel TTS Processing Feature Flag
ENABLE_PARALLEL_TTS = os.getenv("ENABLE_PARALLEL_TTS", "true").lower() == "true"

# Legacy Multi-Voice Generation Feature Flag
# Controls whether to use ContentAnalysisService for explicit multi-voice data population
# ChunkToneService is the preferred method, so this defaults to False
ENABLE_LEGACY_MULTIVOICE = (
    os.getenv("ENABLE_LEGACY_MULTIVOICE", "false").lower() == "true"
)

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

# Logging Configuration
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{levelname} {asctime} {module} {process:d} {thread:d} {message}",
            "style": "{",
        },
        "simple": {
            "format": "{levelname} {message}",
            "style": "{",
        },
        "detailed": {
            "format": "[{asctime}] {levelname} {name} - {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "level": "INFO",
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
        "django_file": {
            "level": "INFO",
            "class": "logging.FileHandler",
            "filename": BASE_DIR / "logs" / "django.log",
            "formatter": "detailed",
        },
        "worker_file": {
            "level": "INFO",
            "class": "logging.FileHandler",
            "filename": BASE_DIR / "logs" / "worker.log",
            "formatter": "detailed",
        },
        "tts_file": {
            "level": "INFO",
            "class": "logging.FileHandler",
            "filename": BASE_DIR / "logs" / "tts_api.log",
            "formatter": "detailed",
        },
    },
    "loggers": {
        "django": {
            "handlers": ["console", "django_file"],
            "level": "INFO",
            "propagate": True,
        },
        "text_to_audio.tasks": {
            "handlers": ["console", "worker_file", "tts_file"],
            "level": "INFO",
            "propagate": False,
        },
        "text_to_audio": {
            "handlers": ["console", "django_file"],
            "level": "INFO",
            "propagate": False,
        },
    },
}

# Session Configuration
SESSION_ENGINE = "django.contrib.sessions.backends.db"  # Store sessions in database
SESSION_COOKIE_AGE = 1209600  # 2 weeks
SESSION_SAVE_EVERY_REQUEST = True  # Extend session on each request
SESSION_EXPIRE_AT_BROWSER_CLOSE = False  # Keep sessions after browser close
SESSION_COOKIE_HTTPONLY = True  # Security: prevent JS access to session cookie
SESSION_COOKIE_SECURE = False  # Set to True in production with HTTPS
SESSION_COOKIE_SAMESITE = "Lax"  # CSRF protection

# Article Processing Settings
ARTICLE_PROCESSING_TIMEOUT_SECONDS = 3600  # 1 hour
# Maximum number of words to analyze for content analysis (reduced from 750k for cost/performance)
MAX_ANALYSIS_WORDS = int(os.environ.get("MAX_ANALYSIS_WORDS", "8000"))

# Parallel TTS Processing Settings
# Maximum concurrent TTS chunks per article
CELERY_TTS_CHUNK_CONCURRENCY = int(os.environ.get("CELERY_TTS_CHUNK_CONCURRENCY", "4"))
# Rate limiting for OpenAI API calls
OPENAI_TTS_RATE_LIMIT_PER_MINUTE = int(
    os.environ.get("OPENAI_TTS_RATE_LIMIT_PER_MINUTE", "50")
)
OPENAI_TTS_RATE_LIMIT_PER_SECOND = int(
    os.environ.get("OPENAI_TTS_RATE_LIMIT_PER_SECOND", "3")
)
# Worker configuration
CELERY_TTS_WORKER_CONCURRENCY = int(
    os.environ.get("CELERY_TTS_WORKER_CONCURRENCY", "2")
)

# Parallel TTS timeout configuration (in seconds)
PARALLEL_TTS_CHORD_TIMEOUT = int(
    os.environ.get("PARALLEL_TTS_CHORD_TIMEOUT", "3600")
)  # 1 hour
PARALLEL_TTS_FINALIZE_TIMEOUT = int(
    os.environ.get("PARALLEL_TTS_FINALIZE_TIMEOUT", "300")
)  # 5 minutes
