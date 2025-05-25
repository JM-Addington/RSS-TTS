"""Fix migration tree inconsistencies.

This migration ensures a proper tree structure by combining fixes for:
1. Duplicate 0011 migrations
2. Reference to non-existent 0010_article_voice
3. Issues with merged migrations in 0012
"""

from django.db import migrations


class Migration(migrations.Migration):
    """Migration to completely fix migration tree issues."""

    dependencies = [
        # Reference both 0011 migrations directly
        ("text_to_audio", "0011_article_multi_voice_data"),
        ("text_to_audio", "0011_uservoicepreset_article_voice_preset"),
        # Also reference any other needed migrations
        (
            "text_to_audio",
            "0010_voicemapping_article_detected_tone_article_speed_and_more",
        ),
    ]

    operations = [
        # No actual operations needed, just fixing dependencies
    ]
