# Voice Selection Fix Implementation

I've implemented several fixes to resolve the issue where only the "alloy" voice is being used despite users selecting different voices or presets.

## Fixes Implemented

### 1. Voice Parameter Generation Service Update

In `text_to_audio/services/voice_parameter_generation.py`, I updated the `generate_voice_parameters()` method to ensure both `voice` and `voice_id` fields are synchronized:

```python
# Set the primary voice from the parameters
if "voice_id" in voice_parameters:
    article.voice_id = voice_parameters["voice_id"]
    article.voice = voice_parameters["voice_id"]  # Ensure both voice and voice_id are in sync

# Persist generated parameters on the article
article.save(
    update_fields=[
        "detected_genre",
        "voice_parameters",
        "voice_id",
        "voice",  # Add voice to update_fields
        "speed",
    ]
)
```

This change ensures that when auto-voice is used, both fields are updated together.

### 2. Explicit Default TTS Voice Setting

In `rss_tts/settings.py`, I added explicit settings for TTS model and voice:

```python
# TTS model and voice settings
OPENAI_TTS_MODEL = os.environ.get("OPENAI_TTS_MODEL", "tts-1")
OPENAI_TTS_VOICE = os.environ.get("OPENAI_TTS_VOICE", "alloy")
```

This change makes the default voice configurable through environment variables and ensures there's a clear fallback.

### 3. Data Migration to Sync Existing Records

Created a new migration file `text_to_audio/migrations/0002_sync_voice_fields.py` that:

1. Finds articles where `voice_id` exists but `voice` is "alloy" and updates `voice` to match `voice_id`
2. Finds articles where `voice` is set to a non-default value but `voice_id` is null and updates `voice_id` to match `voice`

```python
def sync_voice_fields(apps, schema_editor):
    """
    Sync the voice and voice_id fields for all articles.
    This is needed because previously only one of the fields might have been set.
    """
    Article = apps.get_model('text_to_audio', 'Article')

    # Update articles where voice_id exists but voice is default or doesn't match voice_id
    articles_to_update = Article.objects.exclude(voice_id__isnull=True).exclude(voice_id='').filter(voice='alloy')
    for article in articles_to_update:
        article.voice = article.voice_id
        article.save(update_fields=['voice'])

    # Update articles where voice exists but voice_id is not set
    articles_to_update_reverse = Article.objects.exclude(voice='alloy').filter(voice_id__isnull=True)
    for article in articles_to_update_reverse:
        article.voice_id = article.voice
        article.save(update_fields=['voice_id'])
```

## How These Fixes Address the Problem

1. **Field Synchronization**: Ensures both `voice` and `voice_id` fields are always kept in sync, eliminating the source of voice selection confusion.

2. **Default Voice Clarity**: Makes the default voice setting explicit and configurable, rather than hardcoded in multiple places.

3. **Historical Data Fix**: The migration ensures all existing articles have consistent voice settings between the two fields.

## Next Steps

After applying these fixes:

1. Run the database migration: `python manage.py migrate`
2. Restart the Celery worker and web server
3. Test voice selection for:
   - Manually set voices
   - Voice presets
   - Auto-voice detection

These changes should ensure that the selected voice is properly saved and used during audio generation instead of defaulting to "alloy" across different parts of the system.
