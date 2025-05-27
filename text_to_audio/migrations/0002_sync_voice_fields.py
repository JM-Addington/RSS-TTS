"""Migration to synchronize voice and voice_id fields in Article model."""

from django.db import migrations


def sync_voice_fields(apps, schema_editor):
    """
    Sync the voice and voice_id fields for all articles.

    This is needed because previously only one of the fields might have been set.
    """
    Article = apps.get_model("text_to_audio", "Article")

    # Update articles where voice_id exists but voice is default or doesn't match voice_id
    articles_to_update = (
        Article.objects.exclude(voice_id__isnull=True)
        .exclude(voice_id="")
        .filter(voice="alloy")
    )
    for article in articles_to_update:
        article.voice = article.voice_id
        article.save(update_fields=["voice"])

    # Update articles where voice exists but voice_id is not set
    articles_to_update_reverse = Article.objects.exclude(voice="alloy").filter(
        voice_id__isnull=True
    )
    for article in articles_to_update_reverse:
        article.voice_id = article.voice
        article.save(update_fields=["voice_id"])


class Migration(migrations.Migration):
    """Synchronize voice and voice_id fields for existing articles."""

    dependencies = [
        ("text_to_audio", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(sync_voice_fields),
    ]
