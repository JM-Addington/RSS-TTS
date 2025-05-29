"""Migration to update all feeds to use auto-generated voice mode."""

from django.db import migrations


def update_feeds_to_auto_voice(apps, schema_editor):
    """
    Change all feeds to use auto-generated voice mode which enables multi-voice functionality.
    
    This ensures existing users can take advantage of the multi-voice feature.
    """
    Feed = apps.get_model("text_to_audio", "Feed")
    # Get the auto voice mode constant, defined in the model
    VOICE_MODE_AUTO = "auto"
    
    # Update all feeds to use auto-generated voice
    updated_count = Feed.objects.all().update(voice_mode=VOICE_MODE_AUTO)


class Migration(migrations.Migration):
    """Update existing feeds to use auto-generated voice mode with multi-voice capabilities."""

    dependencies = [
        ("text_to_audio", "0002_sync_voice_fields"),
    ]

    operations = [
        migrations.RunPython(update_feeds_to_auto_voice),
    ]