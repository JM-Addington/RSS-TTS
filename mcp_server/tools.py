"""CRUD tool definitions for the MCP server.

Full create/list/get/update/delete coverage for the user-owned domain models:
Feed, Article, FollowedFeed, UserVoicePreset. Every query is scoped to the
authenticated token's user; cross-user access surfaces as "not found".

AIDEV-NOTE: keep tool descriptions model-facing — Claude reads them to decide
which tool to call. Validation failures raise ToolError (-> isError result).
"""

from __future__ import annotations

import logging
import os
from typing import Any

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.validators import URLValidator

from text_to_audio.models import (
    VOICE_CHOICES,
    Article,
    Feed,
    FollowedFeed,
    UserVoicePreset,
)
from text_to_audio.tasks import process_article
from text_to_audio.utils import safe_delete_audio_file
from text_to_audio.validators import validate_url_not_ssrf

from .auth import issuer_base
from .registry import (
    READ_SCOPE,
    WRITE_SCOPE,
    ToolError,
    read_annotations,
    register,
    write_annotations,
)

logger = logging.getLogger(__name__)

VALID_VOICE_IDS = {choice[0] for choice in VOICE_CHOICES}
VALID_VOICE_MODES = {choice[0] for choice in Feed.VOICE_MODE_CHOICES}
VALID_TTS_PROVIDERS = {"openai", "google"}
VALID_ARTICLE_STATUSES = {choice[0] for choice in Article.STATUS_CHOICES}

MAX_LIST_LIMIT = 200
DEFAULT_LIST_LIMIT = 50
# Same hard cap the REST API and Celery task enforce (see api_views.py)
MAX_ARTICLE_WORDS = 40000


# ---------------------------------------------------------------------------
# Schema + validation helpers
# ---------------------------------------------------------------------------


def _obj(
    properties: dict[str, Any], required: list[str] | None = None
) -> dict[str, Any]:
    schema: dict[str, Any] = {
        "type": "object",
        "properties": properties,
        "additionalProperties": False,
    }
    if required:
        schema["required"] = required
    return schema


def _require_int(args: dict[str, Any], key: str) -> int:
    value = args.get(key)
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise ToolError(f"'{key}' must be a positive integer.")
    return value


def _optional_str(args: dict[str, Any], key: str, max_length: int) -> str | None:
    if key not in args or args[key] is None:
        return None
    value = args[key]
    if not isinstance(value, str):
        raise ToolError(f"'{key}' must be a string.")
    if len(value) > max_length:
        raise ToolError(f"'{key}' must be at most {max_length} characters.")
    return value


def _validate_public_url(url: str, field: str) -> None:
    try:
        URLValidator(schemes=["http", "https"])(url)
        validate_url_not_ssrf(url)
    except ValidationError as exc:
        raise ToolError(f"'{field}' is not an allowed URL: {'; '.join(exc.messages)}")


def _get_owned(model: type, user: User, pk: int, label: str) -> Any:
    instance = model.objects.filter(pk=pk, user=user).first()
    if instance is None:
        raise ToolError(f"{label} {pk} not found.")
    return instance


def _limit(args: dict[str, Any]) -> int:
    limit = args.get("limit", DEFAULT_LIST_LIMIT)
    if not isinstance(limit, int) or isinstance(limit, bool) or limit < 1:
        raise ToolError("'limit' must be a positive integer.")
    return min(limit, MAX_LIST_LIMIT)


# AIDEV-NOTE: isinstance guard before set membership — unhashable JSON values
# (dicts/lists) would otherwise raise TypeError -> 500 (PR #240 review)
def _optional_choice(args: dict[str, Any], key: str, valid: set[str]) -> str | None:
    if key not in args or args[key] is None:
        return None
    value = args[key]
    if not isinstance(value, str) or value not in valid:
        raise ToolError(f"'{key}' must be one of: {', '.join(sorted(valid))}.")
    return value


def _optional_voice(args: dict[str, Any], key: str) -> str | None:
    if key not in args or args[key] is None:
        return None
    value = args[key]
    if not isinstance(value, str) or value not in VALID_VOICE_IDS:
        raise ToolError(f"'{key}' is not a recognized voice id.")
    return value


def _check_word_cap(text_content: str) -> None:
    # AIDEV-NOTE: 40k-word cap must stay in parity with api_views.py / tasks.py
    word_count = len(text_content.split())
    if word_count > MAX_ARTICLE_WORDS:
        raise ToolError(
            f"'text_content' is too long ({word_count:,} words). "
            f"Please limit to {MAX_ARTICLE_WORDS:,} words or less."
        )


def _optional_owned_preset(
    user: User, args: dict[str, Any], key: str
) -> UserVoicePreset | None:
    if key not in args or args[key] is None:
        return None
    return _get_owned(UserVoicePreset, user, _require_int(args, key), "Voice preset")


def _delete_article_audio(article: Article) -> None:
    """Best-effort removal of the article's canonical MP3.

    Mirrors the web ArticleDeleteView: resolve the canonical path, delete via
    the directory-protected helper, and never let cleanup failures block the
    database deletion.
    """
    try:
        path = article.get_canonical_audio_path()
    except ValueError:
        return  # no audio_uuid — nothing was ever rendered
    except Exception:
        logger.exception("Cannot resolve audio path for article %s", article.pk)
        return
    try:
        if os.path.exists(path):
            safe_delete_audio_file(path)
    except Exception:
        logger.warning("Could not delete audio file %s", path, exc_info=True)


# ---------------------------------------------------------------------------
# Serializers
# ---------------------------------------------------------------------------


def _iso(value: Any) -> str | None:
    return value.isoformat() if value else None


def serialize_feed(feed: Feed, article_count: int | None = None) -> dict[str, Any]:
    data: dict[str, Any] = {
        "id": feed.pk,
        "name": feed.name,
        "token": str(feed.token),
        "rss_url": f"{issuer_base()}/feeds/{feed.token}/",
        "voice_mode": feed.voice_mode,
        "tts_provider": feed.tts_provider,
        "inbound_email": feed.inbound_email,
        "default_voice_preset_id": feed.default_voice_preset_id,
        "created_at": _iso(feed.created_at),
    }
    if article_count is not None:
        data["article_count"] = article_count
    return data


def serialize_article(article: Article, include_text: bool = False) -> dict[str, Any]:
    data: dict[str, Any] = {
        "id": article.pk,
        "feed_id": article.feed_id,
        "title": article.title,
        "status": article.status,
        "source_url": article.source_url,
        "voice": article.voice,
        "voice_id": article.voice_id,
        "voice_preset_id": article.voice_preset_id,
        "speed": article.speed,
        "summary": article.summary,
        "error_message": article.error_message,
        "audio_uuid": str(article.audio_uuid) if article.audio_uuid else None,
        "audio_url": (
            f"{issuer_base()}/audio/{article.audio_uuid}/"
            if article.audio_uuid and article.status == Article.COMPLETED
            else None
        ),
        "audio_duration": article.audio_duration,
        "created_at": _iso(article.created_at),
        "updated_at": _iso(article.updated_at),
    }
    if include_text:
        data["text_content"] = article.text_content
    return data


def serialize_followed_feed(followed: FollowedFeed) -> dict[str, Any]:
    return {
        "id": followed.pk,
        "url": followed.url,
        "destination_feed_id": followed.destination_feed_id,
        "fetch_full_text": followed.fetch_full_text,
        "is_active": followed.is_active,
        "last_checked": _iso(followed.last_checked),
        "created_at": _iso(followed.created_at),
        "updated_at": _iso(followed.updated_at),
    }


def serialize_voice_preset(preset: UserVoicePreset) -> dict[str, Any]:
    return {
        "id": preset.pk,
        "name": preset.name,
        "voice_id": preset.voice_id,
        "speed": preset.speed,
        "affect": preset.affect,
        "tone": preset.tone,
        "pacing": preset.pacing,
        "pitch_variation": preset.pitch_variation,
        "speaking_style": preset.speaking_style,
        "prompt": preset.prompt,
        "description": preset.description,
        "created_at": _iso(preset.created_at),
        "updated_at": _iso(preset.updated_at),
    }


# ---------------------------------------------------------------------------
# Feed CRUD
# ---------------------------------------------------------------------------


@register(
    "create_feed",
    title="Create feed",
    description=(
        "Create a new podcast feed. Returns the feed including its private "
        "RSS URL, which any podcast app can subscribe to."
    ),
    input_schema=_obj(
        {
            "name": {"type": "string", "maxLength": 100, "description": "Feed name."},
            "voice_mode": {
                "type": "string",
                "enum": sorted(VALID_VOICE_MODES),
                "description": "Voice selection mode for new articles.",
            },
            "tts_provider": {
                "type": "string",
                "enum": sorted(VALID_TTS_PROVIDERS),
                "description": "TTS provider override (defaults to global setting).",
            },
            "default_voice_preset_id": {
                "type": "integer",
                "description": (
                    "Id of an owned voice preset to narrate new articles "
                    "with (sets voice_mode to single_custom)."
                ),
            },
        },
        required=["name"],
    ),
    scope=WRITE_SCOPE,
    annotations=write_annotations(destructive=False, idempotent=False),
)
def create_feed(user: User, args: dict[str, Any]) -> dict[str, Any]:
    name = _optional_str(args, "name", 100)
    if not name or not name.strip():
        raise ToolError("'name' is required and must be a non-empty string.")
    voice_mode = _validated_voice_mode(args)
    tts_provider = _validated_tts_provider(args)
    preset = _optional_owned_preset(user, args, "default_voice_preset_id")
    # AIDEV-NOTE: processing honors default_voice_preset only in single_custom
    # mode (voice_configuration.py) — couple them so the preset takes effect
    if preset is not None:
        if voice_mode is None:
            voice_mode = Feed.VOICE_MODE_SINGLE_CUSTOM
        elif voice_mode != Feed.VOICE_MODE_SINGLE_CUSTOM:
            raise ToolError(
                "'default_voice_preset_id' requires voice_mode 'single_custom' "
                "(omit voice_mode to set it automatically)."
            )
    feed = Feed.objects.create(
        user=user,
        name=name.strip(),
        voice_mode=voice_mode or Feed.VOICE_MODE_AUTO,
        tts_provider=tts_provider,
        default_voice_preset=preset,
    )
    return serialize_feed(feed)


@register(
    "list_feeds",
    title="List feeds",
    description="List all podcast feeds owned by the authenticated user.",
    input_schema=_obj({}),
    scope=READ_SCOPE,
    annotations=read_annotations(),
)
def list_feeds(user: User, args: dict[str, Any]) -> dict[str, Any]:
    feeds = Feed.objects.filter(user=user).order_by("-created_at")
    return {"feeds": [serialize_feed(feed) for feed in feeds]}


@register(
    "get_feed",
    title="Get feed",
    description="Get a single feed by id, including its article count.",
    input_schema=_obj(
        {"feed_id": {"type": "integer", "description": "Feed id."}},
        required=["feed_id"],
    ),
    scope=READ_SCOPE,
    annotations=read_annotations(),
)
def get_feed(user: User, args: dict[str, Any]) -> dict[str, Any]:
    feed = _get_owned(Feed, user, _require_int(args, "feed_id"), "Feed")
    return serialize_feed(feed, article_count=feed.articles.count())


@register(
    "update_feed",
    title="Update feed",
    description=(
        "Update a feed's name, voice mode, TTS provider, or default voice "
        "preset (pass default_voice_preset_id null to clear it)."
    ),
    input_schema=_obj(
        {
            "feed_id": {"type": "integer", "description": "Feed id."},
            "name": {"type": "string", "maxLength": 100},
            "voice_mode": {"type": "string", "enum": sorted(VALID_VOICE_MODES)},
            "tts_provider": {"type": "string", "enum": sorted(VALID_TTS_PROVIDERS)},
            "default_voice_preset_id": {
                "type": ["integer", "null"],
                "description": (
                    "Owned voice preset id (sets voice_mode to single_custom), "
                    "or null to clear it (reverts voice_mode to auto)."
                ),
            },
        },
        required=["feed_id"],
    ),
    scope=WRITE_SCOPE,
    annotations=write_annotations(destructive=False, idempotent=True),
)
def update_feed(user: User, args: dict[str, Any]) -> dict[str, Any]:
    feed = _get_owned(Feed, user, _require_int(args, "feed_id"), "Feed")
    name = _optional_str(args, "name", 100)
    if name is not None:
        if not name.strip():
            raise ToolError("'name' must be a non-empty string.")
        feed.name = name.strip()
    voice_mode = _validated_voice_mode(args)
    if voice_mode is not None:
        feed.voice_mode = voice_mode
    if "tts_provider" in args:
        feed.tts_provider = _validated_tts_provider(args)
    if "default_voice_preset_id" in args:
        preset = _optional_owned_preset(user, args, "default_voice_preset_id")
        feed.default_voice_preset = preset
        # Keep voice_mode consistent so the preset actually takes effect
        # (or stops applying) — see voice_configuration.py gating.
        if preset is not None:
            if voice_mode is not None and voice_mode != Feed.VOICE_MODE_SINGLE_CUSTOM:
                raise ToolError(
                    "'default_voice_preset_id' requires voice_mode "
                    "'single_custom' (omit voice_mode to set it automatically)."
                )
            feed.voice_mode = Feed.VOICE_MODE_SINGLE_CUSTOM
        elif voice_mode is None and feed.voice_mode == Feed.VOICE_MODE_SINGLE_CUSTOM:
            feed.voice_mode = Feed.VOICE_MODE_AUTO
    feed.save()
    return serialize_feed(feed)


@register(
    "delete_feed",
    title="Delete feed",
    description=(
        "Permanently delete a feed AND all of its articles and audio metadata. "
        "This cannot be undone."
    ),
    input_schema=_obj(
        {"feed_id": {"type": "integer", "description": "Feed id."}},
        required=["feed_id"],
    ),
    scope=WRITE_SCOPE,
    annotations=write_annotations(destructive=True, idempotent=True),
)
def delete_feed(user: User, args: dict[str, Any]) -> dict[str, Any]:
    feed_id = _require_int(args, "feed_id")
    feed = _get_owned(Feed, user, feed_id, "Feed")
    # Remove rendered MP3s before the cascade delete drops the article rows.
    for article in feed.articles.all():
        _delete_article_audio(article)
    feed.delete()
    return {"deleted": True, "id": feed_id}


def _validated_voice_mode(args: dict[str, Any]) -> str | None:
    return _optional_choice(args, "voice_mode", VALID_VOICE_MODES)


def _validated_tts_provider(args: dict[str, Any]) -> str | None:
    return _optional_choice(args, "tts_provider", VALID_TTS_PROVIDERS)


# ---------------------------------------------------------------------------
# Article CRUD
# ---------------------------------------------------------------------------


@register(
    "create_article",
    title="Create article",
    description=(
        "Submit an article to a feed for text-to-speech conversion. Provide "
        "either 'source_url' (content is fetched and the title extracted "
        "automatically) or 'title' plus 'text_content'. Processing is "
        "asynchronous: the article starts in PROCESSING status; poll "
        "get_article until it is COMPLETED."
    ),
    input_schema=_obj(
        {
            "feed_id": {"type": "integer", "description": "Destination feed id."},
            "title": {"type": "string", "maxLength": 1024},
            "text_content": {"type": "string", "description": "Raw article text."},
            "source_url": {
                "type": "string",
                "description": "Public http(s) URL to fetch the article from.",
            },
            "voice": {
                "type": "string",
                "description": "Voice id to narrate with (defaults per feed).",
            },
            "speed": {"type": "number", "minimum": 0.25, "maximum": 4.0},
            "voice_preset_id": {
                "type": "integer",
                "description": "Id of an owned voice preset to narrate with.",
            },
        },
        required=["feed_id"],
    ),
    scope=WRITE_SCOPE,
    annotations=write_annotations(destructive=False, idempotent=False),
)
def create_article(user: User, args: dict[str, Any]) -> dict[str, Any]:
    feed = _get_owned(Feed, user, _require_int(args, "feed_id"), "Feed")
    title = (_optional_str(args, "title", 1024) or "").strip()
    text_content = args.get("text_content")
    if text_content is not None and not isinstance(text_content, str):
        raise ToolError("'text_content' must be a string.")
    text_content = text_content or ""
    source_url = (_optional_str(args, "source_url", 2000) or "").strip()

    if not source_url and not text_content:
        raise ToolError("Provide 'source_url' or 'title' + 'text_content'.")
    if text_content and not source_url and not title:
        raise ToolError("'title' is required when submitting raw 'text_content'.")
    if source_url:
        _validate_public_url(source_url, "source_url")
    if text_content:
        _check_word_cap(text_content)

    voice = _optional_voice(args, "voice")
    speed = args.get("speed")
    if speed is not None:
        if not isinstance(speed, (int, float)) or isinstance(speed, bool):
            raise ToolError("'speed' must be a number.")
        if not 0.25 <= float(speed) <= 4.0:
            raise ToolError("'speed' must be between 0.25 and 4.0.")
    preset = _optional_owned_preset(user, args, "voice_preset_id")

    article = Article(
        feed=feed,
        title=title,
        text_content=text_content,
        source_url=source_url,
        status=Article.PROCESSING,
    )
    if voice is not None:
        article.voice = voice
    if speed is not None:
        article.speed = float(speed)
    if preset is not None:
        article.voice_preset = preset
    try:
        article.full_clean(exclude=["audio_uuid", "voice_id"])
    except ValidationError as exc:
        raise ToolError(f"Validation failed: {'; '.join(exc.messages)}")
    article.save()
    process_article.delay(article.pk)
    return serialize_article(article)


@register(
    "list_articles",
    title="List articles",
    description=(
        "List the user's articles, newest first. Optionally filter by feed_id "
        "and/or status (PROCESSING, COMPLETED, FAILED). Text content is "
        "omitted; use get_article for the full body."
    ),
    input_schema=_obj(
        {
            "feed_id": {"type": "integer", "description": "Filter to one feed."},
            "status": {"type": "string", "enum": sorted(VALID_ARTICLE_STATUSES)},
            "limit": {
                "type": "integer",
                "minimum": 1,
                "maximum": MAX_LIST_LIMIT,
                "default": DEFAULT_LIST_LIMIT,
            },
        }
    ),
    scope=READ_SCOPE,
    annotations=read_annotations(),
)
def list_articles(user: User, args: dict[str, Any]) -> dict[str, Any]:
    articles = Article.objects.filter(feed__user=user).order_by("-created_at")
    if "feed_id" in args:
        articles = articles.filter(
            feed=_get_owned(Feed, user, _require_int(args, "feed_id"), "Feed")
        )
    status = _optional_choice(args, "status", VALID_ARTICLE_STATUSES)
    if status is not None:
        articles = articles.filter(status=status)
    return {"articles": [serialize_article(a) for a in articles[: _limit(args)]]}


@register(
    "get_article",
    title="Get article",
    description=(
        "Get a single article by id, including its full text content, "
        "processing status, and audio URL when completed."
    ),
    input_schema=_obj(
        {"article_id": {"type": "integer", "description": "Article id."}},
        required=["article_id"],
    ),
    scope=READ_SCOPE,
    annotations=read_annotations(),
)
def get_article(user: User, args: dict[str, Any]) -> dict[str, Any]:
    article = _get_owned_article(user, _require_int(args, "article_id"))
    return serialize_article(article, include_text=True)


@register(
    "update_article",
    title="Update article",
    description=(
        "Update an article's title, text content, or summary. Does NOT "
        "regenerate audio; resubmit with create_article for a new narration."
    ),
    input_schema=_obj(
        {
            "article_id": {"type": "integer", "description": "Article id."},
            "title": {"type": "string", "maxLength": 1024},
            "text_content": {"type": "string"},
            "summary": {"type": "string"},
        },
        required=["article_id"],
    ),
    scope=WRITE_SCOPE,
    annotations=write_annotations(destructive=False, idempotent=True),
)
def update_article(user: User, args: dict[str, Any]) -> dict[str, Any]:
    article = _get_owned_article(user, _require_int(args, "article_id"))
    title = _optional_str(args, "title", 1024)
    if title is not None:
        article.title = title
    if "text_content" in args and args["text_content"] is not None:
        if not isinstance(args["text_content"], str):
            raise ToolError("'text_content' must be a string.")
        _check_word_cap(args["text_content"])
        article.text_content = args["text_content"]
    if "summary" in args and args["summary"] is not None:
        if not isinstance(args["summary"], str):
            raise ToolError("'summary' must be a string.")
        article.summary = args["summary"]
    article.save()
    return serialize_article(article, include_text=True)


@register(
    "delete_article",
    title="Delete article",
    description="Permanently delete an article. This cannot be undone.",
    input_schema=_obj(
        {"article_id": {"type": "integer", "description": "Article id."}},
        required=["article_id"],
    ),
    scope=WRITE_SCOPE,
    annotations=write_annotations(destructive=True, idempotent=True),
)
def delete_article(user: User, args: dict[str, Any]) -> dict[str, Any]:
    article_id = _require_int(args, "article_id")
    article = _get_owned_article(user, article_id)
    _delete_article_audio(article)
    article.delete()
    return {"deleted": True, "id": article_id}


def _get_owned_article(user: User, article_id: int) -> Article:
    article = (
        Article.objects.select_related("feed")
        .filter(pk=article_id, feed__user=user)
        .first()
    )
    if article is None:
        raise ToolError(f"Article {article_id} not found.")
    return article


# ---------------------------------------------------------------------------
# FollowedFeed CRUD
# ---------------------------------------------------------------------------


@register(
    "create_followed_feed",
    title="Follow an RSS feed",
    description=(
        "Follow an external RSS feed: new entries are automatically converted "
        "to audio and added to the destination feed."
    ),
    input_schema=_obj(
        {
            "url": {"type": "string", "description": "RSS/Atom feed URL."},
            "destination_feed_id": {
                "type": "integer",
                "description": "Feed that receives converted articles.",
            },
            "fetch_full_text": {"type": "boolean", "default": True},
            "is_active": {"type": "boolean", "default": True},
        },
        required=["url", "destination_feed_id"],
    ),
    scope=WRITE_SCOPE,
    annotations=write_annotations(destructive=False, idempotent=False),
)
def create_followed_feed(user: User, args: dict[str, Any]) -> dict[str, Any]:
    url = args.get("url")
    if not isinstance(url, str) or not url.strip():
        raise ToolError("'url' is required and must be a non-empty string.")
    url = url.strip()
    if len(url) > 2000:
        raise ToolError("'url' must be at most 2000 characters.")
    _validate_public_url(url, "url")
    destination = _get_owned(
        Feed, user, _require_int(args, "destination_feed_id"), "Feed"
    )
    if FollowedFeed.objects.filter(
        user=user, url=url, destination_feed=destination
    ).exists():
        raise ToolError("Already following this feed for that destination.")
    followed = FollowedFeed.objects.create(
        user=user,
        url=url,
        destination_feed=destination,
        fetch_full_text=_optional_bool(args, "fetch_full_text", True),
        is_active=_optional_bool(args, "is_active", True),
    )
    return serialize_followed_feed(followed)


@register(
    "list_followed_feeds",
    title="List followed RSS feeds",
    description="List all external RSS feeds the user follows.",
    input_schema=_obj({}),
    scope=READ_SCOPE,
    annotations=read_annotations(),
)
def list_followed_feeds(user: User, args: dict[str, Any]) -> dict[str, Any]:
    followed = FollowedFeed.objects.filter(user=user).order_by("-created_at")
    return {"followed_feeds": [serialize_followed_feed(f) for f in followed]}


@register(
    "get_followed_feed",
    title="Get followed RSS feed",
    description="Get a single followed RSS feed by id.",
    input_schema=_obj(
        {"followed_feed_id": {"type": "integer"}},
        required=["followed_feed_id"],
    ),
    scope=READ_SCOPE,
    annotations=read_annotations(),
)
def get_followed_feed(user: User, args: dict[str, Any]) -> dict[str, Any]:
    followed = _get_owned(
        FollowedFeed, user, _require_int(args, "followed_feed_id"), "Followed feed"
    )
    return serialize_followed_feed(followed)


@register(
    "update_followed_feed",
    title="Update followed RSS feed",
    description=(
        "Update a followed RSS feed's URL, destination, active state, or "
        "full-text fetching."
    ),
    input_schema=_obj(
        {
            "followed_feed_id": {"type": "integer"},
            "url": {"type": "string"},
            "destination_feed_id": {"type": "integer"},
            "fetch_full_text": {"type": "boolean"},
            "is_active": {"type": "boolean"},
        },
        required=["followed_feed_id"],
    ),
    scope=WRITE_SCOPE,
    annotations=write_annotations(destructive=False, idempotent=True),
)
def update_followed_feed(user: User, args: dict[str, Any]) -> dict[str, Any]:
    followed = _get_owned(
        FollowedFeed, user, _require_int(args, "followed_feed_id"), "Followed feed"
    )
    if "url" in args and args["url"] is not None:
        if not isinstance(args["url"], str):
            raise ToolError("'url' must be a string.")
        url = args["url"].strip()
        if len(url) > 2000:
            raise ToolError("'url' must be at most 2000 characters.")
        _validate_public_url(url, "url")
        followed.url = url
    if "destination_feed_id" in args:
        followed.destination_feed = _get_owned(
            Feed, user, _require_int(args, "destination_feed_id"), "Feed"
        )
    if "fetch_full_text" in args:
        followed.fetch_full_text = _optional_bool(args, "fetch_full_text", True)
    if "is_active" in args:
        followed.is_active = _optional_bool(args, "is_active", True)
    # Pre-check the unique constraint so a duplicate (url, destination) pair
    # is a clean validation error rather than an IntegrityError -> -32603.
    if (
        FollowedFeed.objects.filter(
            user=user, url=followed.url, destination_feed=followed.destination_feed
        )
        .exclude(pk=followed.pk)
        .exists()
    ):
        raise ToolError("Already following this feed for that destination.")
    followed.save()
    return serialize_followed_feed(followed)


@register(
    "delete_followed_feed",
    title="Unfollow RSS feed",
    description=(
        "Stop following an external RSS feed. Already-converted articles are " "kept."
    ),
    input_schema=_obj(
        {"followed_feed_id": {"type": "integer"}},
        required=["followed_feed_id"],
    ),
    scope=WRITE_SCOPE,
    annotations=write_annotations(destructive=True, idempotent=True),
)
def delete_followed_feed(user: User, args: dict[str, Any]) -> dict[str, Any]:
    followed_feed_id = _require_int(args, "followed_feed_id")
    followed = _get_owned(FollowedFeed, user, followed_feed_id, "Followed feed")
    followed.delete()
    return {"deleted": True, "id": followed_feed_id}


def _optional_bool(args: dict[str, Any], key: str, default: bool) -> bool:
    value = args.get(key, default)
    if not isinstance(value, bool):
        raise ToolError(f"'{key}' must be a boolean.")
    return value


# ---------------------------------------------------------------------------
# UserVoicePreset CRUD
# ---------------------------------------------------------------------------

_PRESET_TEXT_FIELDS = {
    "affect": 50,
    "tone": 100,
    "pacing": 50,
    "pitch_variation": 50,
}
_PRESET_LONG_FIELDS = ("speaking_style", "prompt", "sample_input", "description")


@register(
    "create_voice_preset",
    title="Create voice preset",
    description=(
        "Create a reusable narration voice preset (voice, speed, and styling "
        "hints) that can be assigned to feeds and articles."
    ),
    input_schema=_obj(
        {
            "name": {"type": "string", "maxLength": 100},
            "voice_id": {
                "type": "string",
                "description": "One of the supported OpenAI/Google voice ids.",
            },
            "speed": {
                "type": "number",
                "minimum": 0.25,
                "maximum": 4.0,
                "default": 1.0,
            },
            "affect": {"type": "string", "maxLength": 50},
            "tone": {"type": "string", "maxLength": 100},
            "pacing": {"type": "string", "maxLength": 50},
            "pitch_variation": {"type": "string", "maxLength": 50},
            "speaking_style": {"type": "string"},
            "prompt": {"type": "string"},
            "sample_input": {"type": "string"},
            "description": {"type": "string"},
        },
        required=["name", "voice_id"],
    ),
    scope=WRITE_SCOPE,
    annotations=write_annotations(destructive=False, idempotent=False),
)
def create_voice_preset(user: User, args: dict[str, Any]) -> dict[str, Any]:
    name = (_optional_str(args, "name", 100) or "").strip()
    if not name:
        raise ToolError("'name' is required and must be a non-empty string.")
    voice_id = _optional_voice(args, "voice_id")
    if voice_id is None:
        raise ToolError("'voice_id' is not a recognized voice id.")
    if UserVoicePreset.objects.filter(user=user, name=name).exists():
        raise ToolError(f"A voice preset named '{name}' already exists.")
    preset = UserVoicePreset(user=user, name=name, voice_id=voice_id)
    _apply_preset_fields(preset, args)
    preset.save()
    return serialize_voice_preset(preset)


@register(
    "list_voice_presets",
    title="List voice presets",
    description="List the user's saved voice presets.",
    input_schema=_obj({}),
    scope=READ_SCOPE,
    annotations=read_annotations(),
)
def list_voice_presets(user: User, args: dict[str, Any]) -> dict[str, Any]:
    presets = UserVoicePreset.objects.filter(user=user).order_by("name")
    return {"voice_presets": [serialize_voice_preset(p) for p in presets]}


@register(
    "get_voice_preset",
    title="Get voice preset",
    description="Get a single voice preset by id.",
    input_schema=_obj(
        {"preset_id": {"type": "integer"}},
        required=["preset_id"],
    ),
    scope=READ_SCOPE,
    annotations=read_annotations(),
)
def get_voice_preset(user: User, args: dict[str, Any]) -> dict[str, Any]:
    preset = _get_owned(
        UserVoicePreset, user, _require_int(args, "preset_id"), "Voice preset"
    )
    return serialize_voice_preset(preset)


@register(
    "update_voice_preset",
    title="Update voice preset",
    description="Update a voice preset's name, voice, speed, or styling hints.",
    input_schema=_obj(
        {
            "preset_id": {"type": "integer"},
            "name": {"type": "string", "maxLength": 100},
            "voice_id": {"type": "string"},
            "speed": {"type": "number", "minimum": 0.25, "maximum": 4.0},
            "affect": {"type": "string", "maxLength": 50},
            "tone": {"type": "string", "maxLength": 100},
            "pacing": {"type": "string", "maxLength": 50},
            "pitch_variation": {"type": "string", "maxLength": 50},
            "speaking_style": {"type": "string"},
            "prompt": {"type": "string"},
            "sample_input": {"type": "string"},
            "description": {"type": "string"},
        },
        required=["preset_id"],
    ),
    scope=WRITE_SCOPE,
    annotations=write_annotations(destructive=False, idempotent=True),
)
def update_voice_preset(user: User, args: dict[str, Any]) -> dict[str, Any]:
    preset = _get_owned(
        UserVoicePreset, user, _require_int(args, "preset_id"), "Voice preset"
    )
    name = _optional_str(args, "name", 100)
    if name is not None:
        name = name.strip()
        if not name:
            raise ToolError("'name' must be a non-empty string.")
        if (
            UserVoicePreset.objects.filter(user=user, name=name)
            .exclude(pk=preset.pk)
            .exists()
        ):
            raise ToolError(f"A voice preset named '{name}' already exists.")
        preset.name = name
    voice_id = _optional_voice(args, "voice_id")
    if voice_id is not None:
        preset.voice_id = voice_id
    _apply_preset_fields(preset, args)
    preset.save()
    return serialize_voice_preset(preset)


@register(
    "delete_voice_preset",
    title="Delete voice preset",
    description=(
        "Delete a voice preset. Feeds and articles referencing it fall back "
        "to default voice settings."
    ),
    input_schema=_obj(
        {"preset_id": {"type": "integer"}},
        required=["preset_id"],
    ),
    scope=WRITE_SCOPE,
    annotations=write_annotations(destructive=True, idempotent=True),
)
def delete_voice_preset(user: User, args: dict[str, Any]) -> dict[str, Any]:
    preset_id = _require_int(args, "preset_id")
    preset = _get_owned(UserVoicePreset, user, preset_id, "Voice preset")
    preset.delete()
    return {"deleted": True, "id": preset_id}


def _apply_preset_fields(preset: UserVoicePreset, args: dict[str, Any]) -> None:
    speed = args.get("speed")
    if speed is not None:
        if not isinstance(speed, (int, float)) or isinstance(speed, bool):
            raise ToolError("'speed' must be a number.")
        if not 0.25 <= float(speed) <= 4.0:
            raise ToolError("'speed' must be between 0.25 and 4.0.")
        preset.speed = float(speed)
    for field_name, max_length in _PRESET_TEXT_FIELDS.items():
        value = _optional_str(args, field_name, max_length)
        if value is not None:
            setattr(preset, field_name, value)
    for field_name in _PRESET_LONG_FIELDS:
        if field_name in args and args[field_name] is not None:
            if not isinstance(args[field_name], str):
                raise ToolError(f"'{field_name}' must be a string.")
            setattr(preset, field_name, args[field_name])
