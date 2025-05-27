"""Migration to set feeds to auto voice mode for multi-voice support."""

from django.db import migrations


def update_feeds_to_auto_voice(apps, schema_editor):
    """
    Update all feeds to use auto-generated voice mode.

    This enables multi-voice functionality for all feeds, which creates a more
    engaging listening experience by using different voices for different parts
    of articles (narration, quotes, etc.).
    """
    Feed = apps.get_model("text_to_audio", "Feed")

    # "auto" is the voice mode constant that enables multi-voice
    VOICE_MODE_AUTO = "auto"

    # Update all feeds to use auto voice mode
    Feed.objects.all().update(voice_mode=VOICE_MODE_AUTO)


class Migration(migrations.Migration):
    """Migration to enable auto voice mode for multi-voice support."""

    dependencies = [
        ("text_to_audio", "0002_sync_voice_fields"),
    ]

    operations = [
        migrations.RunPython(update_feeds_to_auto_voice),
    ]
