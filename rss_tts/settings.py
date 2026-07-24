"""Django settings for rss_tts project."""

import os
import re
from pathlib import Path

import dj_database_url
from django.http import request as django_request

from text_to_audio.services.logging_setup import configure_logging

# AIDEV-NOTE: Patch Django's host validation regex to allow underscores in hostnames.
# This is needed for Docker internal networking where container names like 'caddy_internal'
# contain underscores, violating RFC 952/1123 but required for container-to-container communication.
django_request.host_validation_re = re.compile(
    r"^([a-z0-9._-]+|\[[a-f0-9:]+\])(:[0-9]+)?$", re.IGNORECASE
)

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
OPENAI_TTS_MODEL = os.environ.get("OPENAI_TTS_MODEL", "tts-1-hd")
OPENAI_TTS_VOICE = os.environ.get("OPENAI_TTS_VOICE", "alloy")
OPENAI_TTS_RESPONSE_FORMAT = os.environ.get("OPENAI_TTS_RESPONSE_FORMAT", "wav")
# Models used for content analysis and genre classification
OPENAI_ANALYSIS_MODEL = os.environ.get("OPENAI_ANALYSIS_MODEL", "gpt-4.1")
OPENAI_CLASSIFICATION_MODEL = os.environ.get(
    "OPENAI_CLASSIFICATION_MODEL", "gpt-4o-mini"
)

# URL extraction settings
USE_GPT_FOR_URL_EXTRACTION = os.environ.get(
    "USE_GPT_FOR_URL_EXTRACTION", "True"
).lower() in ("1", "true", "yes")

# Firecrawl settings
FIRECRAWL_API_KEY = os.environ.get("FIRECRAWL_API_KEY")
USE_FIRECRAWL_BY_DEFAULT = os.environ.get(
    "USE_FIRECRAWL_BY_DEFAULT", "False"
).lower() in ("1", "true", "yes")

# ChunkTone LLM Service Feature Flag
ENABLE_CHUNK_TONE_LLM = os.getenv("ENABLE_CHUNK_TONE_LLM", "true").lower() == "true"

# Mailgun settings (for email-to-article ingestion)
MAILGUN_API_KEY = os.environ.get("MAILGUN_API_KEY")
MAILGUN_DOMAIN = os.environ.get("MAILGUN_DOMAIN")
MAILGUN_WEBHOOK_SIGNING_KEY = os.environ.get("MAILGUN_WEBHOOK_SIGNING_KEY")

# AIDEV-NOTE: Enable LLM-based email content cleaning to remove boilerplate/ads
# When enabled, email body text will be processed by LLM to extract main content
# Set to 'true' to enable, anything else (or unset) disables it
ENABLE_EMAIL_CONTENT_CLEANING = os.environ.get(
    "ENABLE_EMAIL_CONTENT_CLEANING", "true"
).lower() in ("true", "1", "yes")

# AIDEV-NOTE: caddy_internal is always allowed for Docker internal health checks/proxying
# The underscore in the hostname violates RFC but is common in Docker container naming
ALLOWED_HOSTS: list[str] = ["caddy_internal"]
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
    "drf_spectacular",
    "widget_tweaks",
    "oauth2_provider",
    "appconfig",
    "accounts",
    "text_to_audio",
    "mcp_server",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "accounts.middleware.AdminApprovalRequiredMiddleware",
    "text_to_audio.middleware.RateLimitMiddleware",
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

# Cache configuration (used by django-ratelimit for rate limiting)
# AIDEV-NOTE: Uses Redis when REDIS_CACHE_URL is set (Docker/prod), falls back to LocMemCache (CI/testing)
REDIS_CACHE_URL = os.environ.get("REDIS_CACHE_URL", "")
if REDIS_CACHE_URL:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.redis.RedisCache",
            "LOCATION": REDIS_CACHE_URL,
        }
    }
else:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        }
    }

# django-ratelimit settings
RATELIMIT_USE_CACHE = "default"
# AIDEV-NOTE: RATELIMIT_EXCEPTION must be True so @ratelimit(block=True) raises
# Ratelimited instead of returning 403, letting RateLimitMiddleware return 429.
RATELIMIT_EXCEPTION = True

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

# Django REST Framework settings
# AIDEV-NOTE: Rate limits: 30/min anon, 60/min auth — tune if bulk submission needed (#189)
REST_FRAMEWORK = {
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "EXCEPTION_HANDLER": "text_to_audio.exception_handler.api_exception_handler",
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 20,
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "anon": "30/minute",
        "user": "60/minute",
    },
}

# drf-spectacular configuration
SPECTACULAR_SETTINGS = {
    "TITLE": "RSS-TTS API",
    "VERSION": "1.0.0",
    "DESCRIPTION": "API for the RSS-TTS system that allows converting RSS feeds to audio podcasts",
    "SERVE_INCLUDE_SCHEMA": False,
}

LOGIN_REDIRECT_URL = "home"
LOGIN_URL = "login"
LOGOUT_REDIRECT_URL = "home"

# RSS Feed Settings
PODCAST_IMAGE_URL = os.environ.get("PODCAST_IMAGE_URL", "")
RSS_EXTERNAL_HOSTNAME = os.environ.get("RSS_EXTERNAL_HOSTNAME", "")
SITE_URL = os.environ.get("SITE_URL", "http://localhost:8000")

# MCP server / OAuth 2.1 settings
# AIDEV-NOTE: MCP_ISSUER_URL is the canonical public base URL (issuer + RFC 8707
# resource host). It must match the URL users type into claude.ai exactly.
MCP_ISSUER_URL = os.environ.get("MCP_ISSUER_URL", SITE_URL)

# django-oauth-toolkit: the co-hosted OAuth 2.1 authorization server for /mcp.
# PKCE (S256) is mandatory per the MCP authorization spec (2025-11-25).
OAUTH2_PROVIDER = {
    "PKCE_REQUIRED": True,
    "SCOPES": {
        "mcp:read": "Read your feeds, articles, and voice presets",
        "mcp:write": "Create, update, and delete feeds, articles, and voice presets",
    },
    "DEFAULT_SCOPES": ["mcp:read"],
    "ACCESS_TOKEN_EXPIRE_SECONDS": 3600,  # short-lived, per OAuth 2.1 guidance
    "REFRESH_TOKEN_EXPIRE_SECONDS": 60 * 60 * 24 * 30,
    "ROTATE_REFRESH_TOKEN": True,  # MUST rotate for public clients (OAuth 2.1)
    "REFRESH_TOKEN_GRACE_PERIOD_SECONDS": 120,
    # http is allowed only so RFC 8252 loopback redirects work (Claude Code);
    # the DCR endpoint rejects non-loopback http redirect URIs.
    "ALLOWED_REDIRECT_URI_SCHEMES": ["https", "http"],
}

# Logging setup is imported at the top of the file

# Logging Configuration
LOGGING_BASE = {
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
            "class": "text_to_audio.services.logging_setup.SafeFileHandler",
            "filename": BASE_DIR / "logs" / "django.log",
            "formatter": "detailed",
        },
        "worker_file": {
            "level": "INFO",
            "class": "text_to_audio.services.logging_setup.SafeFileHandler",
            "filename": BASE_DIR / "logs" / "worker.log",
            "formatter": "detailed",
        },
        "tts_file": {
            "level": "INFO",
            "class": "text_to_audio.services.logging_setup.SafeFileHandler",
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

# Apply our safe logging configuration
LOGGING = configure_logging(LOGGING_BASE, BASE_DIR)

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
