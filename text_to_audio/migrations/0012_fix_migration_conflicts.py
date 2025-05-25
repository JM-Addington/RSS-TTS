# Generated manually on 2025-05-25 to fix migration conflicts
"""Empty migration resolving dependency conflicts."""

from django.db import migrations


class Migration(migrations.Migration):
    """Migration to fix migration conflicts."""

    dependencies = [
        ("text_to_audio", "0011_article_multi_voice_data"),
        ("text_to_audio", "0011_uservoicepreset_article_voice_preset"),
    ]

    operations = [
        # No operations needed, just fixing dependencies
    ]
