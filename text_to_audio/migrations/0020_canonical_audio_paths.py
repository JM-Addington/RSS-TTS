# Generated manually for canonical audio path migration

import uuid

from django.db import migrations


def populate_missing_audio_uuids(apps, schema_editor):
    """Populate audio_uuid for articles that don't have one."""
    Article = apps.get_model("text_to_audio", "Article")

    for article in Article.objects.filter(audio_uuid__isnull=True):
        article.audio_uuid = uuid.uuid4()
        article.save(update_fields=["audio_uuid"])


def reverse_populate_missing_audio_uuids(apps, schema_editor):
    """Reverse migration - nothing to do here."""
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("text_to_audio", "0019_establish_voice_single_source_of_truth"),
    ]

    operations = [
        migrations.RunPython(
            populate_missing_audio_uuids,
            reverse_populate_missing_audio_uuids,
        ),
    ]
